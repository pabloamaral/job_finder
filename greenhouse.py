"""Greenhouse source.

Greenhouse exposes a public, documented JSON endpoint per company board:

    https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true

The `content=true` param includes the full HTML job description. This is a
legitimate public API; no auth or scraping required.
"""

from __future__ import annotations

import logging
import re
import time
from html import unescape

import requests

from jobpipeline.models import JobListing
from jobpipeline.sources.base import JobSource

logger = logging.getLogger(__name__)

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"


def _strip_html(raw: str) -> str:
    """Crude HTML -> text. Good enough for keyword matching.

    Swap in a real parser (e.g. selectolax/BeautifulSoup) if you need clean
    text for the cover letter generator.
    """
    text = unescape(raw or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class GreenhouseSource(JobSource):
    """Pulls listings from one or more Greenhouse company boards."""

    name = "greenhouse"

    def __init__(self, company_slugs: list[str], timeout: int = 15,
                 polite_delay: float = 0.5):
        self.company_slugs = company_slugs
        self.timeout = timeout
        self.polite_delay = polite_delay  # gap between company requests

    def _fetch_company(self, slug: str) -> list[JobListing]:
        url = GREENHOUSE_URL.format(slug=slug)
        resp = requests.get(url, timeout=self.timeout,
                            headers={"User-Agent": "job-pipeline/1.0"})
        resp.raise_for_status()
        payload = resp.json()

        listings: list[JobListing] = []
        for job in payload.get("jobs", []):
            location = (job.get("location") or {}).get("name", "")
            description = _strip_html(job.get("content", ""))
            offices = job.get("offices", [])
            department = None
            if job.get("departments"):
                department = job["departments"][0].get("name")

            listings.append(
                JobListing(
                    title=job.get("title", ""),
                    company=slug,  # board slug; refine with a slug->name map
                    location=location,
                    description=description,
                    url=job.get("absolute_url", ""),
                    source=self.name,
                    remote="remote" in location.lower(),
                    department=department,
                    posted_at=job.get("updated_at"),
                    raw=job,
                )
            )
        return listings

    def fetch(self) -> list[JobListing]:
        all_listings: list[JobListing] = []
        for slug in self.company_slugs:
            try:
                company_listings = self._fetch_company(slug)
                logger.info("greenhouse:%s -> %d listings",
                            slug, len(company_listings))
                all_listings.extend(company_listings)
            except requests.RequestException as exc:
                # One bad board shouldn't sink the run.
                logger.warning("greenhouse:%s failed: %s", slug, exc)
            time.sleep(self.polite_delay)
        return all_listings
