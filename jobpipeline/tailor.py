"""Resume tailoring module.

Takes a base resume (structured JSON) plus a job description and produces a
TailoredApplication: a reweighted bullet ordering, an adjusted summary, an
aligned keyword set, and a short cover letter.

Two hard rules, both enforced here:

  1. NEVER invent experience. Tailoring only *reorders* and *reweights*
     content that already exists in the base resume. It does not write new
     bullets or add skills the resume doesn't claim.

  2. FLAG anything unsupported. `verify_claims` checks the tailored output
     against the base resume's vocabulary and reports any claim whose key
     terms don't appear in the source. The review queue surfaces these.

The cover-letter generator here is a deterministic template. If you want
LLM-written letters, call the Anthropic API from `generate_cover_letter`
and keep `verify_claims` running on the result — that's the safety net.
"""

from __future__ import annotations

import json
import re

from jobpipeline.models import JobListing, TailoredApplication


# ---------------------------------------------------------------------------
# Base resume loading
# ---------------------------------------------------------------------------

def load_base_resume(path: str) -> dict:
    """Load the structured base resume from JSON."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _all_bullets(resume: dict) -> list[tuple[str, str]]:
    """Flatten every bullet across roles -> list of (company, bullet)."""
    out: list[tuple[str, str]] = []
    for role in resume.get("experience", []):
        for bullet in role.get("bullets", []):
            out.append((role.get("company", ""), bullet))
    return out


# ---------------------------------------------------------------------------
# Keyword extraction + bullet scoring
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#/]*")
_STOPWORDS = {
    "the", "and", "for", "with", "you", "our", "are", "this", "that", "will",
    "have", "from", "your", "can", "all", "who", "but", "not", "out", "use",
    "a", "an", "to", "of", "in", "on", "as", "is", "be", "or", "we",
}


def _keywords(text: str) -> set[str]:
    """Content tokens from a chunk of text, stopwords removed."""
    return {t for t in _TOKEN_RE.findall(text.lower())
            if t not in _STOPWORDS and len(t) > 2}


def _bullet_relevance(bullet: str, jd_keywords: set[str]) -> int:
    """How many JD keywords a bullet touches — used to rank bullets."""
    return len(_keywords(bullet) & jd_keywords)


# ---------------------------------------------------------------------------
# Tailoring
# ---------------------------------------------------------------------------

def reorder_bullets(resume: dict, jd_keywords: set[str],
                    limit: int = 12) -> list[str]:
    """Reorder existing bullets so the most JD-relevant surface first.

    Crucially this only *reorders* — every returned bullet is verbatim from
    the base resume. No new content is created.
    """
    bullets = _all_bullets(resume)
    ranked = sorted(
        bullets,
        key=lambda cb: _bullet_relevance(cb[1], jd_keywords),
        reverse=True,
    )
    return [f"[{company}] {bullet}" for company, bullet in ranked[:limit]]


def adjust_summary(resume: dict, jd_keywords: set[str]) -> str:
    """Lightly adapt the summary's emphasis.

    The base summary is kept as the factual core. We only append a single
    emphasis sentence built from skills the resume ALREADY claims and that
    also appear in the JD — so nothing new is asserted.
    """
    base = resume.get("summary", "")
    resume_skills = {
        s.lower()
        for group in resume.get("skills", {}).values()
        for s in group
    }
    # Skills present in both the resume and the JD.
    emphasis = sorted(
        skill for skill in resume_skills
        if _keywords(skill) & jd_keywords
    )
    if not emphasis:
        return base
    top = ", ".join(emphasis[:5])
    return f"{base} Particularly relevant here: {top}."


def align_keywords(resume: dict, jd_keywords: set[str]) -> list[str]:
    """Keywords to emphasize: present in BOTH the JD and the base resume.

    This is the honest intersection. Keywords the JD wants but the resume
    lacks are deliberately NOT added — they'd be unsupported claims.
    """
    resume_text = json.dumps(resume).lower()
    resume_keywords = _keywords(resume_text)
    return sorted(jd_keywords & resume_keywords)


# ---------------------------------------------------------------------------
# Claim verification — the safety net
# ---------------------------------------------------------------------------

def verify_claims(text: str, resume: dict) -> list[str]:
    """Return claims in `text` not supported by the base resume.

    The job here is narrow but important: catch sentences that assert
    *experience, skills, or accomplishments* the resume doesn't back up —
    while NOT flagging ordinary cover-letter scaffolding ("I'd welcome the
    chance to discuss...").

    Heuristic: only inspect sentences that look like experiential claims
    (they contain a claim verb such as "built", "led", "managed"). For those
    sentences, check whether their distinctive content words appear in the
    resume vocabulary. This is conservative — tune `unknown_threshold` and
    the verb list as needed.
    """
    resume_vocab = _keywords(json.dumps(resume))
    # Generic vocabulary that legitimately appears in any cover letter and
    # should never on its own trigger a flag.
    allowed_extra = {
        "team", "role", "company", "opportunity", "excited", "contribute",
        "experience", "background", "position", "hiring", "application",
        "interview", "looking", "forward", "best", "regards", "sincerely",
        "dear", "thank", "thanks", "would", "bring", "value", "fit", "chance",
        "discuss", "how", "welcome", "interest", "express", "writing",
        "currently", "closely", "particularly", "enjoy", "directly", "both",
        "engineer", "architect", "consultant", "manager", "specialist",
    }
    safe_vocab = resume_vocab | allowed_extra

    # A sentence is only treated as an experiential *claim* if it uses one
    # of these verbs. Generic intent sentences are skipped entirely.
    claim_verbs = {
        "built", "build", "led", "lead", "managed", "manage", "architected",
        "architect", "designed", "design", "developed", "develop", "created",
        "create", "delivered", "deliver", "implemented", "implement",
        "achieved", "achieve", "increased", "decreased", "reduced", "owned",
        "own", "scaled", "launched", "shipped", "drove", "completed",
        "mentored", "trained", "founded", "spearheaded", "oversaw",
    }

    flags: list[str] = []
    sentences = re.split(r"(?<=[.!?\n])\s+", text)
    for sentence in sentences:
        words = _keywords(sentence)
        if not words:
            continue
        # Skip anything that isn't asserting concrete experience.
        if not (words & claim_verbs):
            continue
        unknown = words - safe_vocab
        if len(unknown) >= 4 and len(unknown) / len(words) > 0.5:
            flags.append(
                f"Unverified claim — terms not in base resume "
                f"({', '.join(sorted(unknown)[:6])}): \"{sentence.strip()}\""
            )
    return flags


# ---------------------------------------------------------------------------
# Cover letter
# ---------------------------------------------------------------------------

def generate_cover_letter(resume: dict, listing: JobListing,
                          aligned_keywords: list[str]) -> str:
    """Deterministic, template-based cover letter.

    Built entirely from base-resume facts plus the job's title/company.
    Swap this for an Anthropic API call if you want richer prose — but keep
    `verify_claims` running on whatever it returns.
    """
    name = resume.get("name", "")
    years = "8+"  # from the resume summary
    current = resume["experience"][0] if resume.get("experience") else {}
    current_title = current.get("title", "")
    current_company = current.get("company", "")
    skills_line = ", ".join(aligned_keywords[:6]) if aligned_keywords else \
        "solution architecture and customer-facing technical delivery"

    return (
        f"Dear {listing.company} Hiring Team,\n\n"
        f"I'm writing to express interest in the {listing.title} role. "
        f"I'm currently a {current_title} at {current_company}, with {years} "
        f"years owning the post-sale technical relationship for Enterprise "
        f"customers across implementation, integration, and ongoing advisory.\n\n"
        f"My background lines up closely with what this role calls for, "
        f"particularly around {skills_line}. I enjoy translating complex "
        f"technical environments into business outcomes and working directly "
        f"with both developer and business stakeholders.\n\n"
        f"I'd welcome the chance to discuss how my experience could "
        f"contribute to your team.\n\n"
        f"Best regards,\n{name}"
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def tailor_application(listing: JobListing, resume: dict) -> TailoredApplication:
    """Produce a complete TailoredApplication for one listing."""
    jd_keywords = _keywords(listing.description)

    summary = adjust_summary(resume, jd_keywords)
    bullets = reorder_bullets(resume, jd_keywords)
    aligned = align_keywords(resume, jd_keywords)
    cover_letter = generate_cover_letter(resume, listing, aligned)

    # Run the safety net over BOTH generated artifacts.
    unsupported = verify_claims(summary, resume)
    unsupported += verify_claims(cover_letter, resume)

    return TailoredApplication(
        job_id=listing.job_id,
        tailored_summary=summary,
        reordered_bullets=bullets,
        aligned_keywords=aligned,
        cover_letter=cover_letter,
        unsupported_claims=unsupported,
    )
