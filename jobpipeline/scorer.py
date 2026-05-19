"""Filter and score module.

Ranks each JobListing against two things:

  1. The role cluster  -> title_score
  2. The owner profile -> profile_score

and combines them into a 0-100 fit_score, with human-readable reasons.

The matcher deliberately treats the target titles as a *cluster*: it
normalizes titles and matches on signal tokens rather than exact strings,
because companies name these roles inconsistently.

This module uses lightweight token overlap so it runs with zero external
dependencies. For better matching you can later swap `_keyword_overlap` for
embeddings (sentence-transformers) without touching the rest of the pipeline.
"""

from __future__ import annotations

import re

from jobpipeline import config
from jobpipeline.models import JobListing, ScoreResult


# ---------------------------------------------------------------------------
# Title normalization + cluster matching
# ---------------------------------------------------------------------------

_NORMALIZE_SUBS = [
    (r"\bsr\.?", "senior"),
    (r"\bjr\.?", "junior"),
    (r"\bii\b", ""),
    (r"\biii\b", ""),
    (r"\biv\b", ""),
    (r"[-/|,.]", " "),
    (r"\s+", " "),
]


def normalize_title(title: str) -> str:
    """Lowercase and canonicalize a job title for loose matching."""
    t = title.lower().strip()
    for pattern, repl in _NORMALIZE_SUBS:
        t = re.sub(pattern, repl, t)
    return t.strip()


def title_cluster_score(title: str) -> tuple[float, list[str]]:
    """Score how well a title fits the target role cluster (0-100).

    Returns (score, reasons). Logic, in priority order:
      - Exact cluster phrase present        -> 100
      - Any role signal token present       -> 70-90 depending on count
      - Excluded token present              -> heavy penalty
      - Nothing                             -> 0
    """
    norm = normalize_title(title)
    reasons: list[str] = []

    # Exclusions first — kill obviously-wrong roles.
    for bad in config.ROLE_EXCLUDE_TOKENS:
        if bad in norm:
            reasons.append(f"Title contains excluded term '{bad.strip()}'")
            return 10.0, reasons

    # Exact cluster phrase.
    for role in config.ROLE_CLUSTER:
        if role in norm:
            reasons.append(f"Title matches target role '{role}'")
            return 100.0, reasons

    # Signal-token matching for loosely-named roles.
    hits = [tok for tok in config.ROLE_SIGNAL_TOKENS if tok in norm]
    if hits:
        # 70 base + 10 per extra signal, capped at 90 (not a clean match).
        score = min(70.0 + 10.0 * (len(hits) - 1), 90.0)
        reasons.append(f"Title shares signal terms: {', '.join(hits)}")
        return score, reasons

    reasons.append("Title does not match the role cluster")
    return 0.0, reasons


# ---------------------------------------------------------------------------
# Profile / JD overlap
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#/]*")


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def profile_overlap_score(description: str) -> tuple[float, list[str], list[str]]:
    """Score JD overlap with the owner profile (0-100).

    Returns (score, matched_keywords, missing_keywords).
    """
    jd_tokens = _tokenize(description)
    jd_text = description.lower()

    # Build the set of profile keywords/phrases worth checking.
    profile_terms: list[str] = []
    profile_terms += config.OWNER_PROFILE["core_skills"]
    profile_terms += config.OWNER_PROFILE["domains"]
    profile_terms += config.OWNER_PROFILE["strengths"]

    matched: list[str] = []
    missing: list[str] = []
    for term in profile_terms:
        # Multi-word terms: substring match. Single words: token match.
        present = (term in jd_text) if " " in term else (term in jd_tokens)
        (matched if present else missing).append(term)

    if not profile_terms:
        return 0.0, [], []

    raw_ratio = len(matched) / len(profile_terms)
    # A JD won't mention every skill; calibrate so ~40% overlap reads as strong.
    score = min(raw_ratio / 0.4, 1.0) * 100.0
    return round(score, 1), matched, missing


# ---------------------------------------------------------------------------
# Combined scoring
# ---------------------------------------------------------------------------

def score_listing(listing: JobListing) -> ScoreResult:
    """Produce a full ScoreResult for a single listing."""
    title_score, title_reasons = title_cluster_score(listing.title)
    profile_score, matched, missing = profile_overlap_score(listing.description)

    fit = (
        title_score * config.SCORING["title_weight"]
        + profile_score * config.SCORING["profile_weight"]
    )

    reasons = list(title_reasons)
    if matched:
        top = matched[:8]
        reasons.append(f"JD overlaps owner profile on: {', '.join(top)}")
    if profile_score < 30:
        reasons.append("Weak overlap with owner profile — review carefully")

    if listing.remote:
        fit = min(fit + config.SCORING["remote_bonus"], 100.0)
        reasons.append("Remote role (+bonus)")

    return ScoreResult(
        fit_score=round(fit, 1),
        title_score=round(title_score, 1),
        profile_score=round(profile_score, 1),
        matched_keywords=matched,
        missing_keywords=missing,
        reasons=reasons,
    )


def filter_and_score(listings: list[JobListing]) -> list[tuple[JobListing, ScoreResult]]:
    """Score every listing and return them sorted by fit, descending.

    Note this does not drop low scorers — the caller decides the threshold.
    Keeping everything lets the tracker record 'seen but skipped' jobs.
    """
    scored = [(lst, score_listing(lst)) for lst in listings]
    scored.sort(key=lambda pair: pair[1].fit_score, reverse=True)
    return scored
