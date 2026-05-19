"""Listing filters driven by config."""

from __future__ import annotations

from jobpipeline.models import JobListing


def is_remote_listing(listing: JobListing) -> bool:
    """True when the role is remote-only (not hybrid or on-site)."""
    loc = listing.location.lower().strip()
    if "hybrid" in loc:
        return False
    return listing.remote or "remote" in loc


def filter_remote_only(listings: list[JobListing]) -> list[JobListing]:
    return [lst for lst in listings if is_remote_listing(lst)]
