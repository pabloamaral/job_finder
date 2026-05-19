"""Core data models for the job application pipeline.

These dataclasses are the shared vocabulary between every module. Sources
produce JobListing objects; the scorer attaches a ScoreResult; the tailor
produces TailoredApplication; the tracker persists everything.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ApplicationStatus(str, Enum):
    """Lifecycle states for a job in the review queue."""

    NEW = "new"
    REVIEWED = "reviewed"
    APPLIED = "applied"
    REJECTED = "rejected"
    SKIPPED = "skipped"


@dataclass
class JobListing:
    """A single job posting discovered from a source.

    `job_id` is a stable, deterministic hash so the same posting from the
    same company is never surfaced twice, even across runs.
    """

    title: str
    company: str
    location: str
    description: str
    url: str
    source: str  # e.g. "greenhouse", "lever"
    remote: bool = False
    department: Optional[str] = None
    posted_at: Optional[str] = None
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    raw: dict = field(default_factory=dict)  # original payload, kept for debugging

    @property
    def job_id(self) -> str:
        """Deterministic ID derived from company + title + url."""
        key = f"{self.company.lower()}|{self.title.lower()}|{self.url}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["job_id"] = self.job_id
        return d


@dataclass
class ScoreResult:
    """Output of the filter/score module for one listing."""

    fit_score: float  # 0-100
    title_score: float  # how well the title matches the role cluster
    profile_score: float  # how well the JD matches the owner profile
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TailoredApplication:
    """Output of the resume tailoring module."""

    job_id: str
    tailored_summary: str
    reordered_bullets: list[str] = field(default_factory=list)
    aligned_keywords: list[str] = field(default_factory=list)
    cover_letter: str = ""
    # Claims in the tailored docs not backed by the base resume. Must stay
    # empty for an honest application; the review UI surfaces these loudly.
    unsupported_claims: list[str] = field(default_factory=list)
    resume_path: Optional[str] = None  # path to generated file, if any

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PipelineRecord:
    """The unit the tracker persists: a job plus everything derived from it."""

    listing: JobListing
    score: Optional[ScoreResult] = None
    application: Optional[TailoredApplication] = None
    status: ApplicationStatus = ApplicationStatus.NEW
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "listing": self.listing.to_dict(),
            "score": self.score.to_dict() if self.score else None,
            "application": self.application.to_dict() if self.application else None,
            "status": self.status.value,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineRecord":
        listing = JobListing(**{k: v for k, v in d["listing"].items()
                                if k != "job_id"})
        score = ScoreResult(**d["score"]) if d.get("score") else None
        application = (
            TailoredApplication(**d["application"]) if d.get("application") else None
        )
        return cls(
            listing=listing,
            score=score,
            application=application,
            status=ApplicationStatus(d.get("status", "new")),
            updated_at=d.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )
