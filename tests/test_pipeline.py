"""Tests for the scoring and tailoring modules.

Run with:  python -m pytest tests/  -q
These cover the matcher's cluster logic and — most importantly — the
"never invent experience" guarantee in the tailor.
"""

import json
import os
import tempfile

import pytest

from jobpipeline.filters import is_remote_listing
from jobpipeline.models import JobListing
from jobpipeline.scorer import (
    normalize_title,
    title_cluster_score,
    score_listing,
)
from jobpipeline.tailor import (
    tailor_application,
    verify_claims,
    align_keywords,
)


# --- fixtures --------------------------------------------------------------

BASE_RESUME = {
    "name": "Pablo Amaral",
    "summary": "Solutions Architect with 8+ years owning the post sale "
               "technical relationship for Enterprise customers.",
    "skills": {
        "Languages": ["SQL", "Python", "REST APIs"],
        "Cloud": ["Snowflake", "BigQuery", "AWS"],
    },
    "experience": [
        {
            "title": "Solutions Architect",
            "company": "Simon AI",
            "bullets": [
                "Architect end-to-end migrations from Snowflake into the CDP.",
                "Build custom Python integrations connecting client APIs.",
            ],
        },
    ],
}


def _listing(**kwargs):
    defaults = dict(
        title="Solutions Architect",
        company="TestCo",
        location="Remote",
        description=(
            "We need Python and Snowflake skills for cloud data migration "
            "and API integration work."
        ),
        url="https://example.com/job/1",
        source="test",
    )
    defaults.update(kwargs)
    lst = JobListing(**defaults)
    if "remote" not in kwargs:
        lst.remote = "remote" in defaults["location"].lower()
    return lst


# --- title normalization + cluster matching --------------------------------

def test_normalize_strips_seniority_markers():
    assert normalize_title("Sr. Solutions Architect II") == "senior solutions architect"


def test_exact_cluster_title_scores_max():
    score, reasons = title_cluster_score("Solutions Engineer")
    assert score == 100.0
    assert any("matches target role" in r for r in reasons)


def test_loose_title_matches_via_signal_tokens():
    # Not an exact cluster phrase but clearly in-cluster.
    score, _ = title_cluster_score("Technical Solutions Specialist")
    assert 70.0 <= score <= 90.0


def test_excluded_title_is_penalized():
    score, _ = title_cluster_score("Solutions Marketing Manager")
    assert score <= 10.0


def test_unrelated_title_scores_zero():
    score, _ = title_cluster_score("Warehouse Associate")
    assert score == 0.0


# --- combined scoring ------------------------------------------------------

def test_score_listing_produces_full_result():
    result = score_listing(_listing())
    assert 0 <= result.fit_score <= 100
    assert result.matched_keywords  # JD mentions python/snowflake
    assert result.reasons


def test_is_remote_listing():
    assert is_remote_listing(_listing(location="Remote - US"))
    assert is_remote_listing(_listing(location="United States (Remote)"))
    assert not is_remote_listing(_listing(location="San Francisco, CA"))
    assert not is_remote_listing(_listing(location="Hybrid - Remote"))
    assert not is_remote_listing(_listing(location="Costa Rica"))


def test_remote_role_gets_bonus():
    remote = _listing()
    remote.remote = True
    onsite = _listing()
    onsite.remote = False
    assert score_listing(remote).fit_score >= score_listing(onsite).fit_score


# --- tailoring: the honesty guarantees -------------------------------------

def test_aligned_keywords_only_from_resume():
    """Aligned keywords must be the intersection of JD and resume — never
    keywords the JD wants but the resume lacks."""
    jd_keywords = {"python", "snowflake", "kubernetes", "rust"}
    aligned = align_keywords(BASE_RESUME, jd_keywords)
    # python + snowflake are in the resume; kubernetes + rust are not.
    assert "python" in aligned
    assert "snowflake" in aligned
    assert "kubernetes" not in aligned
    assert "rust" not in aligned


def test_tailored_bullets_are_verbatim_from_resume():
    """Reordered bullets must be exact resume content, only reordered."""
    app = tailor_application(_listing(), BASE_RESUME)
    source_bullets = {
        b for role in BASE_RESUME["experience"] for b in role["bullets"]
    }
    for tailored in app.reordered_bullets:
        # Tailored bullets are prefixed with "[Company] " — strip and check.
        raw = tailored.split("] ", 1)[-1]
        assert raw in source_bullets, f"Invented bullet: {raw}"


def test_verify_claims_flags_invented_content():
    invented = ("I led a 50-person blockchain quantum cryptography division "
                "at NASA building rocket telemetry systems.")
    flags = verify_claims(invented, BASE_RESUME)
    assert flags, "verify_claims should flag clearly invented experience"


def test_verify_claims_passes_resume_grounded_content():
    grounded = ("I have experience with Python and Snowflake migrations.")
    flags = verify_claims(grounded, BASE_RESUME)
    assert not flags, f"Resume-grounded text should not be flagged: {flags}"


def test_tailored_application_reports_unsupported_claims_field():
    app = tailor_application(_listing(), BASE_RESUME)
    # The field must always exist (even if empty) for the review UI.
    assert isinstance(app.unsupported_claims, list)


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
