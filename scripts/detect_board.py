#!/usr/bin/env python3
"""Detect ATS type and board slug from a careers or job-board URL.

Usage:
    python scripts/detect_board.py https://boards.greenhouse.io/stripe
    python scripts/detect_board.py https://jobs.ashbyhq.com/notion
    python scripts/detect_board.py https://jobs.lever.co/netflix

Optionally probes public APIs to confirm the board exists.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests

# (regex on URL path/host, ats name, config list name)
_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"boards\.greenhouse\.io/([^/?#]+)", re.I), "greenhouse", "GREENHOUSE_COMPANIES"),
    (re.compile(r"boards-api\.greenhouse\.io/v1/boards/([^/?#]+)", re.I), "greenhouse", "GREENHOUSE_COMPANIES"),
    (re.compile(r"jobs\.lever\.co/([^/?#]+)", re.I), "lever", "LEVER_COMPANIES"),
    (re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)", re.I), "ashby", "ASHBY_COMPANIES"),
    (re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([^/?#]+)", re.I), "ashby", "ASHBY_COMPANIES"),
]

_PROBE_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
}


@dataclass
class BoardMatch:
    ats: str
    slug: str
    config_key: str


def detect_from_url(url: str) -> list[BoardMatch]:
    matches: list[BoardMatch] = []
    seen: set[tuple[str, str]] = set()
    for pattern, ats, config_key in _PATTERNS:
        for hit in pattern.findall(url):
            slug = hit.rstrip("/").lower()
            key = (ats, slug)
            if key in seen:
                continue
            seen.add(key)
            matches.append(BoardMatch(ats=ats, slug=slug, config_key=config_key))
    return matches


def probe_board(ats: str, slug: str, timeout: int = 10) -> tuple[bool, str]:
    template = _PROBE_URLS.get(ats)
    if not template:
        return False, "no probe for this ATS"
    url = template.format(slug=slug)
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "job-pipeline/1.0"},
        )
        if resp.status_code == 404:
            return False, "board not found (404)"
        resp.raise_for_status()
        data = resp.json()
        if ats == "greenhouse":
            count = len(data.get("jobs", []))
        elif ats == "lever":
            count = len(data) if isinstance(data, list) else 0
        else:
            count = len(data.get("jobs", []))
        return True, f"ok ({count} jobs)"
    except requests.RequestException as exc:
        return False, str(exc)


def format_config_snippet(match: BoardMatch) -> str:
    return f'    "{match.slug}",  # add to {match.config_key}'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="+", help="careers or job board URL(s)")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="HTTP-check that the public API returns jobs",
    )
    args = parser.parse_args(argv)

    any_found = False
    for url in args.url:
        print(f"\n{url}")
        matches = detect_from_url(url)
        if not matches:
            host = urlparse(url).netloc
            print(f"  No Greenhouse / Lever / Ashby slug detected in URL ({host}).")
            print("  Open the careers page and look for jobs.ashbyhq.com, boards.greenhouse.io,")
            print("  or jobs.lever.co in the apply link, then pass that URL here.")
            continue

        any_found = True
        for match in matches:
            line = f"  {match.ats}: {match.slug}  ->  {match.config_key}"
            if args.probe:
                ok, detail = probe_board(match.ats, match.slug)
                line += f"  [{detail}]" if ok else f"  [probe failed: {detail}]"
            print(line)
            print(f"  {format_config_snippet(match)}")

    return 0 if any_found else 1


if __name__ == "__main__":
    sys.exit(main())
