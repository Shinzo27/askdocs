"""Regression tests for the parser traps listed in AGENTS.md ("Known traps").

Each test pins one bug that has already cost the corpus real sections or chunks.
Stdlib unittest, so it runs on a clean machine with no pip:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import ingest


class SectionHeaderInline(unittest.TestCase):
    """`inline` style: "80C. Deduction in respect of ..." on one line."""

    def test_plain_and_footnote_prefixed_headers_match(self):
        for line in (
            "80C. Deduction in respect of life insurance premia",
            "4[80C. Deduction in respect of life insurance premia",   # Windows poppler
            "[80C. Deduction in respect of life insurance premia",    # poppler 24.02 lifts the "4"
            "     [80C. Deduction in respect of life insurance premia",
            "*80C. Deduction in respect of life insurance premia",
        ):
            with self.subTest(line=line):
                m = ingest.SECTION_RE.match(line)
                self.assertIsNotNone(m)
                self.assertEqual(m.group(1), "80C")

    def test_lowercase_continuation_is_not_a_header(self):
        self.assertIsNone(ingest.SECTION_RE.match("80C. of the said Act shall apply"))

    def test_numbered_list_inside_a_section_does_not_start_one(self):
        page = ("80C. Deduction in respect of life insurance premia.\n"
                "(a) 12. Something listed inside the section body\n")
        sections = {r[0] for r in ingest.scan_rows([page], "inline") if r[0]}
        self.assertEqual(sections, {"80C"})


class SectionHeaderAbove(unittest.TestCase):
    """`above` style (2025 Act gazette): title line, then "9.(1) body"."""

    def test_number_with_no_space_before_subsection(self):
        # Trap 2: requiring whitespace after the dot dropped 23 sections.
        for line, want in (("9.(1) The total income", "9"), ("536.(1) The Income-tax Act", "536"),
                           ("13. Where any income", "13"), ("12A.", "12A")):
            with self.subTest(line=line):
                m = ingest.NUM_HEAD_RE.match(line)
                self.assertIsNotNone(m)
                self.assertEqual(m.group(1), want)

    def test_decimal_is_not_a_section_number(self):
        self.assertIsNone(ingest.NUM_HEAD_RE.match("9.5 per cent of the amount"))

    def test_gap_fill_and_schedules_get_their_own_keys(self):
        # A joined line list keeps the fixture readable; an f-string would not.
        page = "\n".join([  # noqa: FLY002
            "Short title and commencement.",
            "1.(1) This Act may be called the Test Act.",
            "Definitions.",
            "2.(1) In this Act, unless the context otherwise requires.",
            "Charge of tax.",
            "3. Tax shall be charged on the total income.",   # no (1): only gap-fill finds it
            "Scope of total income.",
            "4.(1) Total income includes all income.",
            "SCHEDULE I",
            "1. First row of the schedule table.",            # must not restart section 1
        ])
        rows = ingest.scan_rows_above([page])
        # A section starts at its number line; the title line above it is kept
        # as section_title (it trails the previous section's text).
        self.assertEqual([r[0] for r in rows],
                         [None, "1", "1", "2", "2", "3", "3", "4", "SCHEDULE I", "SCHEDULE I"])
        titles = {r[0]: r[1] for r in rows if r[0]}
        self.assertEqual(titles["3"], "Charge of tax")
        self.assertEqual(titles["4"], "Scope of total income")
        # Trap 4: without SCHEDULE keys the table would cite the last section.
        self.assertEqual(rows[-1][1], "Schedule I")


class TocDetection(unittest.TestCase):
    def test_arrangement_page_is_toc(self):
        page = "ARRANGEMENT OF SECTIONS\n" + "\n".join(
            f"{n}. Title of section number {n}" for n in range(1, 9))
        self.assertTrue(ingest.is_toc_page(page))

    def test_body_page_with_many_inline_headers_is_not_toc(self):
        # Trap 3: rule-PDF body pages reference many sections but wrap long prose.
        body = "\n".join(
            f"{n}. Application for registration under this rule shall be made in the form "
            f"specified and verified by the authorised signatory of the applicant concerned."
            for n in range(1, 11))
        self.assertFalse(ingest.is_toc_page(body))

    def test_bounded_mode_needs_an_explicit_heading(self):
        table = "\n".join(f"{n}. Row {n} of a definitions table" for n in range(1, 12))
        self.assertFalse(ingest.is_toc_page(table, bounded=True))


class Packing(unittest.TestCase):
    def test_chunks_respect_the_cap_and_drop_furniture(self):
        long_para = "word " * 1000
        chunks = ingest.pack(["tiny", long_para.strip()])
        self.assertTrue(chunks)
        self.assertTrue(all(len(c) <= ingest.MAX_CHARS for c in chunks))
        self.assertTrue(all(len(c) >= ingest.MIN_CHUNK for c in chunks))


if __name__ == "__main__":
    unittest.main()
