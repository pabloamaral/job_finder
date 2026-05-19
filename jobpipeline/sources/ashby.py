"""Ashby source.

Public JSON per company board:

    https://api.ashbyhq.com/posting-api/job-board/{slug}
"""

from __future__ import annotations

import logging
import time

import requests

from jobpipeline.models import JobListing
from jobpipeline.sources._text import strip_html
from jobpipeline.sources.base import JobSource

logger = logging.getLogger(__name__)

ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def _ashby_remote(job: dict) -> bool:
    workplace = (job.get("workplaceType") or "").lower()
    location = (job.get("location") or "").lower()
    if workplace == "hybrid":
        return False
    if workplace == "remote":
        return True
    if job.get("isRemote") and "hybrid" not in workplace:
        return True
    return "remote" in location


class AshbySource(JobSource):
    """Pulls listings from Ashby-hosted company boards."""

    name = "ashby"

    def __init__(
        self,
        company_slugs: list[str],
        timeout: int = 15,
        polite_delay: float = 0.5,
    ):
        self.company_slugs = company_slugs
        self.timeout = timeout
        self.polite_delay = polite_delay

    def _fetch_company(self, slug: str) -> list[JobListing]:
        url = ASHBY_URL.format(slug=slug)
        resp = requests.get(
            url,
            timeout=self.timeout,
            headers={"User-Agent": "job-pipeline/1.0"},
        )
        resp.raise_for_status()
        payload = resp.json()

        listings: list[JobListing] = []
        for job in payload.get("jobs", []):
            if not job.get("isListed", True):
                continue
            location = job.get("location") or ""
            description = job.get("descriptionPlain") or strip_html(
                job.get("descriptionHtml", "")
            )
            listings.append(
                JobListing(
                    title=(job.get("title") or "").strip(),
                    company=slug,
                    location=location,
                    description=description,
                    url=job.get("jobUrl") or job.get("applyUrl", ""),
                    source=self.name,
                    remote=_ashby_remote(job),
                    department=job.get("department") or job.get("team"),
                    posted_at=job.get("publishedAt"),
                    raw=job,
                )
            )
        return listings

    def fetch(self) -> list[JobListing]:
        all_listings: list[JobListing] = []
        for slug in self.company_slugs:
            try:
                company_listings = self._fetch_company(slug)
                logger.info("ashby:%s -> %d listings", slug, len(company_listings))
                all_listings.extend(company_listings)
            except requests.RequestException as exc:
                logger.warning("ashby:%s failed: %s", slug, exc)
            time.sleep(self.polite_delay)
        return all_listings
