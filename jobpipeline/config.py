"""Configuration for the job pipeline.

Centralizes the things you'll tune most often: the role cluster, the owner
profile keywords, and which companies to poll. Keeping this as a Python
module (rather than YAML) means you can compute things and get IDE support;
swap to a file loader later if you want non-developers editing it.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# ROLE CLUSTER
# ---------------------------------------------------------------------------
# These titles are treated as a related cluster, not exact strings. The
# matcher should normalize ("Sr.", "II", "-", etc.) and match loosely.
ROLE_CLUSTER: list[str] = [
    "solutions architect",
    "sales engineer",
    "forward deployed engineer",
    "solutions engineer",
    "customer engineer",
    "implementation engineer",
    "technical account manager",
    "solutions consultant",
    "field engineer",
    "deployment engineer",
    "presales engineer",
    "technical solutions engineer",
]

# Tokens that, if present in a title, strongly suggest the role is in-cluster
# even if the exact phrase differs.
ROLE_SIGNAL_TOKENS: list[str] = [
    "solutions",
    "sales engineer",
    "forward deployed",
    "presales",
    "pre-sales",
    "customer engineer",
    "implementation",
    "technical account",
    "deployment",
    "field engineer",
]

# Titles to actively exclude even if they contain signal tokens
# (e.g. "Solutions Marketing Manager" is not what we want).
ROLE_EXCLUDE_TOKENS: list[str] = [
    "marketing",
    "recruiter",
    "intern",
    "manager, sales",  # people-managing sales roles
    "director",
    "vp ",
    "vice president",
]


# ---------------------------------------------------------------------------
# OWNER PROFILE
# ---------------------------------------------------------------------------
# Drawn directly from the base resume. The scorer rewards JD overlap with
# these; the tailor uses them for keyword alignment. Keep factual.
OWNER_PROFILE: dict = {
    "name": "Pablo Amaral",
    "years_experience": 8,
    "core_skills": [
        "sql",
        "python",
        "javascript",
        "rest apis",
        "snowflake",
        "bigquery",
        "redshift",
        "databricks",
        "aws",
        "google cloud",
        "git",
        "github",
        "cursor",
        "ci/cd",
        "etl",
        "elt",
        "data migration",
        "api integration",
        "oauth",
        "embedded analytics",
    ],
    "domains": [
        "post-sale technical relationship",
        "solution architecture",
        "implementation",
        "customer enablement",
        "technical advisory",
        "cloud data warehouses",
        "bi and analytics",
        "poc design",
    ],
    "strengths": [
        "customer-facing",
        "translating technical concepts for business stakeholders",
        "enterprise accounts",
        "cross-functional leadership",
    ],
}


# ---------------------------------------------------------------------------
# SOURCES
# ---------------------------------------------------------------------------
# Greenhouse and Lever expose public JSON per company. The "slug" is the
# identifier in the board URL, e.g. boards.greenhouse.io/<slug>.
GREENHOUSE_COMPANIES: list[str] = [
    "anthropic",
    "databricks",
    "snowflake",
    "stripe",
    # add company board slugs here
]

LEVER_COMPANIES: list[str] = [
    # e.g. "netflix", "spotify" — add lever.co board slugs here
]


# ---------------------------------------------------------------------------
# LOCATION
# ---------------------------------------------------------------------------
# When True, discovery and the review queue only include remote roles.
REMOTE_ONLY = True


# ---------------------------------------------------------------------------
# SCORING WEIGHTS
# ---------------------------------------------------------------------------
SCORING = {
    "title_weight": 0.45,    # how much title-cluster fit matters
    "profile_weight": 0.55,  # how much JD/profile overlap matters
    "min_score_to_tailor": 60.0,  # don't waste tailoring effort below this
    "remote_bonus": 5.0,     # small nudge for remote roles
}


# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "pipeline.db")
BASE_RESUME_PATH = os.path.join(BASE_DIR, "resume", "base_resume.json")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "applications")
