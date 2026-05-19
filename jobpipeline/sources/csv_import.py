"""CSV import source for manually added jobs (e.g. from LinkedIn).

Expected columns: title, company, location, url, description
Optional: department
"""

from __future__ import annotations

import csv
import logging
import os

from jobpipeline.models import JobListing
from jobpipeline.sources.base import JobSource

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ("title", "company", "location", "url", "description")


class CsvImportSource(JobSource):
    """Reads job postings from a CSV file on disk."""

    name = "csv"

    def __init__(self, csv_path: str):
        self.csv_path = csv_path

    def fetch(self) -> list[JobListing]:
        if not os.path.isfile(self.csv_path):
            logger.info("csv: no file at %s (skipping)", self.csv_path)
            return []

        listings: list[JobListing] = []
        with open(self.csv_path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                logger.warning("csv: empty file %s", self.csv_path)
                return []
            missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
            if missing:
                logger.warning(
                    "csv: missing columns %s in %s (need %s)",
                    missing,
                    self.csv_path,
                    list(REQUIRED_COLUMNS),
                )
                return []

            for row_num, row in enumerate(reader, start=2):
                title = (row.get("title") or "").strip()
                if not title:
                    continue
                location = (row.get("location") or "").strip()
                listings.append(
                    JobListing(
                        title=title,
                        company=(row.get("company") or "").strip(),
                        location=location,
                        description=(row.get("description") or "").strip(),
                        url=(row.get("url") or "").strip(),
                        source=self.name,
                        remote="remote" in location.lower(),
                        department=(row.get("department") or "").strip() or None,
                    )
                )

        logger.info("csv:%s -> %d listings", self.csv_path, len(listings))
        return listings
