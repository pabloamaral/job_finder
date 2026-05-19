"""Pipeline orchestrator.

Wires the modules into a single discovery run:

    sources -> dedup -> score -> (tailor if score high enough) -> persist

Designed to be run on a schedule (cron, a loop, GitHub Actions). Each run is
idempotent: jobs already in the tracker are skipped, so nothing is
re-surfaced and no work is duplicated.
"""

from __future__ import annotations

import logging

from jobpipeline import config
from jobpipeline.scorer import filter_and_score
from jobpipeline.sources import GreenhouseSource, LeverSource
from jobpipeline.sources.base import JobSource
from jobpipeline.tailor import load_base_resume, tailor_application
from jobpipeline.tracker import Tracker

logger = logging.getLogger(__name__)


def build_sources() -> list[JobSource]:
    """Construct the configured sources. Add new sources here."""
    sources: list[JobSource] = []
    if config.GREENHOUSE_COMPANIES:
        sources.append(GreenhouseSource(config.GREENHOUSE_COMPANIES))
    if config.LEVER_COMPANIES:
        sources.append(LeverSource(config.LEVER_COMPANIES))
    return sources


def run_discovery(tracker: Tracker, tailor: bool = True) -> dict:
    """Run one full discovery cycle.

    Returns a summary dict: counts of discovered / new / scored / tailored.
    """
    sources = build_sources()
    if not sources:
        logger.warning("No sources configured — edit config.py")
        return {"discovered": 0, "new": 0, "tailored": 0}

    # 1. DISCOVER -----------------------------------------------------------
    all_listings = []
    for source in sources:
        all_listings.extend(source.fetch())
    logger.info("Discovered %d listings total", len(all_listings))

    # 2. DEDUP --------------------------------------------------------------
    known = tracker.known_job_ids()
    new_listings = [lst for lst in all_listings if lst.job_id not in known]
    logger.info("%d are new (not previously seen)", len(new_listings))

    # 3. SCORE --------------------------------------------------------------
    scored = filter_and_score(new_listings)

    # 4. TAILOR (only above the configured threshold) + 5. PERSIST ----------
    base_resume = load_base_resume(config.BASE_RESUME_PATH) if tailor else None
    threshold = config.SCORING["min_score_to_tailor"]
    tailored_count = 0

    for listing, score in scored:
        application = None
        if tailor and score.fit_score >= threshold and base_resume:
            application = tailor_application(listing, base_resume)
            tailored_count += 1
        tracker.upsert(listing, score=score, application=application)

    summary = {
        "discovered": len(all_listings),
        "new": len(new_listings),
        "tailored": tailored_count,
    }
    logger.info("Discovery run complete: %s", summary)
    return summary
