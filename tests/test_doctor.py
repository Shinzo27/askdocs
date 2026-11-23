"""Tests for the corpus gate in scripts/doctor.py.

The chunk-count pins are the invariant that caught two silent parser
regressions; these tests make sure the gate itself cannot quietly stop failing.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import doctor

REFERENCE = next(p for p in doctor.PIN_SETS if p["pdftotext"] is None)
UBUNTU = next(p for p in doctor.PIN_SETS if p["pdftotext"] == "24.02.0")
FAQ = "faq-cbdt"


def pin_set_for(build: str | None) -> dict:
    """Select a pin set by build, so adding a machine does not edit the tests."""
    return next(p for p in doctor.PIN_SETS if p["pdftotext"] == build)


def without_faq(pins: dict[str, int]) -> dict[str, int]:
    return {k: v for k, v in pins.items() if k != FAQ}


class PinSets(unittest.TestCase):
    def test_every_pin_set_covers_exactly_the_manifest(self):
        manifest = {d["doc_id"] for d in
                    json.loads(doctor.MANIFEST.read_text(encoding="utf-8"))["documents"]}
        for p in doctor.PIN_SETS:
            with self.subTest(pin_set=p["label"]):
                self.assertEqual(set(p["chunks"]), manifest)

    def test_versions_are_unique(self):
        versions = [p["pdftotext"] for p in doctor.PIN_SETS if p["pdftotext"]]
        self.assertEqual(len(versions), len(set(versions)))


class PinFindings(unittest.TestCase):
    def test_full_corpus_on_a_pinned_build_is_clean(self):
        f = doctor.pin_findings(dict(UBUNTU["chunks"]), "24.02.0")
        self.assertEqual((f.fail, f.warn), ([], []))

    def test_missing_eval_document_warns_but_passes(self):
        f = doctor.pin_findings(without_faq(UBUNTU["chunks"]), "24.02.0")
        self.assertEqual(f.fail, [])
        self.assertTrue(any("NOT comparable" in w for w in f.warn))

    def test_drift_on_a_pinned_build_fails(self):
        counts = dict(UBUNTU["chunks"], **{"it-act-1961": 3741})  # the 24.02 bare-"[" bug
        f = doctor.pin_findings(counts, "24.02.0")
        self.assertEqual(len(f.fail), 1)
        self.assertIn("it-act-1961: 3741 vs 3845", f.fail[0])

    def test_other_builds_pins_do_not_excuse_drift(self):
        # A 24.02 corpus that happens to equal the reference counts is still drift.
        f = doctor.pin_findings(dict(REFERENCE["chunks"]), "24.02.0")
        self.assertTrue(f.fail)

    def test_unrecorded_build_matching_a_set_passes_with_a_warning(self):
        f = doctor.pin_findings(without_faq(REFERENCE["chunks"]), "25.99.0")
        self.assertEqual(f.fail, [])
        self.assertTrue(any("record the version" in w for w in f.warn))

    def test_unrecorded_build_matching_nothing_fails(self):
        counts = dict(REFERENCE["chunks"], **{"cgst-act-2017": 1})
        f = doctor.pin_findings(counts, None)
        self.assertTrue(any("no pin set" in x for x in f.fail))

    def test_empty_stats_fail(self):
        self.assertTrue(doctor.pin_findings({}, "24.02.0").fail)


STATS = doctor.PROCESSED / "stats.json"


@unittest.skipUnless(STATS.exists(), "no local corpus - run fetch_corpus.py + ingest.py")
class LocalCorpus(unittest.TestCase):
    """The asserted chunk counts ADR-011 refers to, against the corpus on disk."""

    def test_local_corpus_matches_its_pins(self):
        stats = json.loads(STATS.read_text(encoding="utf-8"))
        f = doctor.pin_findings(stats.get("chunks_by_doc", {}), stats.get("pdftotext_version"))
        self.assertEqual(f.fail, [])


if __name__ == "__main__":
    unittest.main()
