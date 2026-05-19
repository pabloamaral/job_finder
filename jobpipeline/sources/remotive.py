"""Remotive aggregator source.

Public API (no key): https://remotive.com/api/remote-jobs

Per Remotive terms, link back to remotive.com job URLs and mention Remotive
as the source when republishing listings elsewhere.
"""

from __future__ import annotations

import logging

import requests

from jobpipeline.models import JobListing
from jobpipeline.sources._text import strip_html
from jobpipeline.sources.base import JobSource

logger = logging.getLogger(__name__)

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


class RemotiveSource(JobSource):
    """Fetches remote job listings from Remotive's public API."""

    name = "remotive"

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def fetch(self) -> list[JobListing]:
        resp = requests.get(
            REMOTIVE_URL,
            timeout=self.timeout,
            headers={"User-Agent": "job-pipeline/1.0"},
        )
        resp.raise_for_status()
        payload = resp.json()

        listings: list[JobListing] = []
        for job in payload.get("jobs", []):
            location = job.get("candidate_required_location") or "Remote"
            description = strip_html(job.get("description", ""))
            if job.get("salary"):
                description = f"Salary: {job['salary']}\n\n{description}"
            listings.append(
                JobListing(
                    title=(job.get("title") or "").strip(),
                    company=(job.get("company_name") or "").strip(),
                    location=location,
                    description=description,
                    url=job.get("url", ""),
                    source=self.name,
                    remote=True,
                    department=job.get("category"),
                    posted_at=job.get("publication_date"),
                    raw=job,
                )
            )

        logger.info("remotive -> %d listings", len(listings))
        return listings
