"""Tracker module.

A thin SQLite persistence layer. Responsibilities:

  - Remember every job ever seen, so sources don't re-surface duplicates.
  - Store the score and tailored application alongside each job.
  - Track the status field (new/reviewed/applied/rejected/skipped).
  - Answer "what's in my pipeline right now?" for the review queue.

SQLite is used because it's stdlib, single-file, and zero-setup. The schema
is one table; the derived objects are stored as JSON blobs so the model
classes stay the source of truth.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from jobpipeline.models import (
    ApplicationStatus,
    JobListing,
    PipelineRecord,
    ScoreResult,
    TailoredApplication,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    company      TEXT NOT NULL,
    title        TEXT NOT NULL,
    source       TEXT NOT NULL,
    url          TEXT,
    fit_score    REAL,
    status       TEXT NOT NULL DEFAULT 'new',
    listing_json TEXT NOT NULL,
    score_json   TEXT,
    app_json     TEXT,
    discovered_at TEXT,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_score  ON jobs(fit_score);
"""


class Tracker:
    """SQLite-backed pipeline store. Use as a context manager or call close()."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> "Tracker":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.conn.close()

    # -- dedup --------------------------------------------------------------

    def known_job_ids(self) -> set[str]:
        """All job_ids ever recorded — used to skip re-processing."""
        rows = self.conn.execute("SELECT job_id FROM jobs").fetchall()
        return {r["job_id"] for r in rows}

    def is_known(self, job_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return row is not None

    # -- writes -------------------------------------------------------------

    def upsert(self, listing: JobListing,
               score: ScoreResult | None = None,
               application: TailoredApplication | None = None,
               status: ApplicationStatus | None = None) -> None:
        """Insert or update a job record.

        Existing status is preserved unless `status` is explicitly passed,
        so re-running discovery never clobbers a job you've already actioned.
        """
        now = datetime.now(timezone.utc).isoformat()
        existing = self.conn.execute(
            "SELECT status FROM jobs WHERE job_id = ?", (listing.job_id,)
        ).fetchone()

        final_status = (
            status.value if status is not None
            else (existing["status"] if existing else ApplicationStatus.NEW.value)
        )

        self.conn.execute(
            """
            INSERT INTO jobs (job_id, company, title, source, url, fit_score,
                              status, listing_json, score_json, app_json,
                              discovered_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(job_id) DO UPDATE SET
                fit_score   = excluded.fit_score,
                status      = excluded.status,
                listing_json= excluded.listing_json,
                score_json  = excluded.score_json,
                app_json    = excluded.app_json,
                updated_at  = excluded.updated_at
            """,
            (
                listing.job_id,
                listing.company,
                listing.title,
                listing.source,
                listing.url,
                score.fit_score if score else None,
                final_status,
                json.dumps(listing.to_dict()),
                json.dumps(score.to_dict()) if score else None,
                json.dumps(application.to_dict()) if application else None,
                listing.discovered_at,
                now,
            ),
        )
        self.conn.commit()

    def set_status(self, job_id: str, status: ApplicationStatus) -> bool:
        """Update just the status of a job. Returns False if unknown."""
        now = datetime.now(timezone.utc).isoformat()
        cur = self.conn.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE job_id = ?",
            (status.value, now, job_id),
        )
        self.conn.commit()
        return cur.rowcount > 0

    # -- reads --------------------------------------------------------------

    def _row_to_record(self, row: sqlite3.Row) -> PipelineRecord:
        d = {
            "listing": json.loads(row["listing_json"]),
            "score": json.loads(row["score_json"]) if row["score_json"] else None,
            "application": json.loads(row["app_json"]) if row["app_json"] else None,
            "status": row["status"],
            "updated_at": row["updated_at"],
        }
        return PipelineRecord.from_dict(d)

    def get(self, job_id: str) -> PipelineRecord | None:
        row = self.conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def query(self, status: ApplicationStatus | None = None,
              min_score: float | None = None,
              limit: int = 100) -> list[PipelineRecord]:
        """Fetch pipeline records, optionally filtered. Sorted by fit score."""
        clauses, params = [], []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if min_score is not None:
            clauses.append("fit_score >= ?")
            params.append(min_score)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM jobs {where} "
            f"ORDER BY fit_score DESC NULLS LAST LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def stats(self) -> dict[str, int]:
        """Count of jobs by status — the pipeline-state summary."""
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}
