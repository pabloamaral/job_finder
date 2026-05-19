"""Lever source.

Lever exposes a public JSON endpoint per company:

    https://api.lever.co/v0/postings/{slug}?mode=json

This returns an array of postings with description text, categories
(team, location, commitment), and apply URLs. Public API, no auth needed.
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

LEVER_URL = "https://api.lever.co/v0/postings/{slug}?mode=json"


def _strip_html(raw: str) -> str:
    text = unescape(raw or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|li|div)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class LeverSource(JobSource):
    """Pulls listings from one or more Lever company boards."""

    name = "lever"

    def __init__(self, company_slugs: list[str], timeout: int = 15,
                 polite_delay: float = 0.5):
        self.company_slugs = company_slugs
        self.timeout = timeout
        self.polite_delay = polite_delay

    def _fetch_company(self, slug: str) -> list[JobListing]:
        url = LEVER_URL.format(slug=slug)
        resp = requests.get(url, timeout=self.timeout,
                            headers={"User-Agent": "job-pipeline/1.0"})
        resp.raise_for_status()
        postings = resp.json()  # Lever returns a top-level array

        listings: list[JobListing] = []
        for post in postings:
            categories = post.get("categories", {}) or {}
            location = categories.get("location", "") or ""
            # Lever description: prefer plain text fields, fall back to HTML.
            description = post.get("descriptionPlain") or _strip_html(
                post.get("description", "")
            )
            # Append the structured "lists" (responsibilities, requirements).
            for block in post.get("lists", []):
                description += "\n\n" + block.get("text", "")
                description += "\n" + _strip_html(block.get("content", ""))

            workplace = (post.get("workplaceType") or "").lower()
            listings.append(
                JobListing(
                    title=post.get("text", ""),
                    company=slug,
                    location=location,
                    description=description.strip(),
                    url=post.get("hostedUrl", "") or post.get("applyUrl", ""),
                    source=self.name,
                    remote=workplace == "remote" or "remote" in location.lower(),
                    department=categories.get("team"),
                    posted_at=str(post.get("createdAt", "")),
                    raw=post,
                )
            )
        return listings

    def fetch(self) -> list[JobListing]:
        all_listings: list[JobListing] = []
        for slug in self.company_slugs:
            try:
                company_listings = self._fetch_company(slug)
                logger.info("lever:%s -> %d listings",
                            slug, len(company_listings))
                all_listings.extend(company_listings)
            except requests.RequestException as exc:
                logger.warning("lever:%s failed: %s", slug, exc)
            time.sleep(self.polite_delay)
        return all_listings
