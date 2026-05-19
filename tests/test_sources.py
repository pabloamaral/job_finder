"""Tests for job board sources and URL detection."""

import csv
import tempfile
from pathlib import Path

import pytest

from jobpipeline.sources.ashby import _ashby_remote
from jobpipeline.sources.csv_import import CsvImportSource

# scripts/ is not a package; import detect_board by path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from detect_board import BoardMatch, detect_from_url  # noqa: E402


def test_ashby_remote_detection():
    assert _ashby_remote({"workplaceType": "Remote", "location": "US"})
    assert not _ashby_remote({"workplaceType": "Hybrid", "isRemote": True})
    assert _ashby_remote({"isRemote": True, "workplaceType": "Remote", "location": ""})


def test_csv_import_reads_rows():
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, encoding="utf-8"
    ) as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["title", "company", "location", "url", "description"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "title": "Solutions Architect",
                "company": "Acme",
                "location": "Remote",
                "url": "https://example.com/j/1",
                "description": "Python and Snowflake required.",
            }
        )
        path = fh.name

    listings = CsvImportSource(path).fetch()
    assert len(listings) == 1
    assert listings[0].title == "Solutions Architect"
    assert listings[0].remote is True
    assert listings[0].source == "csv"


def test_csv_import_missing_file():
    assert CsvImportSource("/nonexistent/path/jobs.csv").fetch() == []


@pytest.mark.parametrize(
    "url,ats,slug",
    [
        ("https://boards.greenhouse.io/stripe/jobs/123", "greenhouse", "stripe"),
        ("https://jobs.lever.co/netflix/abc", "lever", "netflix"),
        ("https://jobs.ashbyhq.com/notion/05e14247", "ashby", "notion"),
    ],
)
def test_detect_board_from_url(url: str, ats: str, slug: str):
    matches = detect_from_url(url)
    assert any(m.ats == ats and m.slug == slug for m in matches)
