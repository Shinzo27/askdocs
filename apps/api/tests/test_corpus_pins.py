"""Corpus pins as tests, not just a script.

`scripts/doctor.py` is the gate a human runs; these tests are the gate CI runs on
every push. They read the committed stats (not the gitignored chunk file) so they
work on a machine that has not fetched the PDFs - and fail loudly if a parser
change moves a count without a reviewed re-baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
STATS = ROOT / "data" / "processed" / "stats.json"

EXPECTED = {
    "it-act-2025": 1762,
    "it-rules-2026": 2670,
    "it-act-1961": 3852,
    "cgst-act-2017": 579,
    "cgst-rules-2017": 889,
    "faq-cbdt": 1317,
}


@pytest.fixture(scope="module")
def stats() -> dict:
    if not STATS.exists():
        pytest.skip("data/processed/stats.json absent - run: python scripts/ingest.py")
    return json.loads(STATS.read_text(encoding="utf-8"))


def test_chunk_counts_match_pins(stats: dict) -> None:
    assert stats["chunks_by_doc"] == EXPECTED
    assert stats["chunks"] == sum(EXPECTED.values())


def test_extractor_recorded(stats: dict) -> None:
    """Counts are only comparable inside one extraction binary."""
    assert stats["extractor"]["pdftotext"], "extractor version missing from stats.json"


def test_every_document_declares_a_vintage(stats: dict) -> None:
    for doc_id, entry in stats["documents"].items():
        assert entry["vintage"], f"{doc_id} has no vintage - it cannot be cited honestly"


def test_tax_year_metadata_present(stats: dict) -> None:
    """The whole reason two Acts coexist: `applies_to_ay` is data, not a prompt."""
    applies = {doc: entry["applies_to_ay"] for doc, entry in stats["documents"].items()}
    assert "2026-27 onwards" in applies["it-act-2025"]
    assert "2026-27 and earlier" in applies["it-act-1961"]


def test_unparsed_sections_are_reported_not_hidden(stats: dict) -> None:
    """A parser that lies about coverage is worse than a documented gap."""
    entry = stats["documents"]["it-act-2025"]
    assert entry["sections_unparsed"] == 23
    assert entry["sections_numbered"] + entry["sections_unparsed"] == 536


def test_schedules_are_their_own_sections(stats: dict) -> None:
    """Without this, a deduction table cites 'Section 536 - Repeal and savings'."""
    assert stats["documents"]["it-act-2025"]["sections"] >= stats["documents"]["it-act-2025"][
        "sections_numbered"
    ]
