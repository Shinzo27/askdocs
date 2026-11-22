"""The refusal gate: decide *before* generating whether an answer is even possible.

Two rules from ADR-005 and `docs/ARCHITECTURE.md`:

* short-circuit on a weak top rerank score (τ), an empty retrieval, or a question
  that names a tax year the corpus cannot speak to;
* never let refusal look like an error - it is a correct answer that costs no
  tokens and ~200 ms.

τ is a configuration value (`REFUSAL_SCORE_THRESHOLD`) and changes only with an
eval run attached to the PR that changes it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from askdocs_api.config import get_settings
from askdocs_api.prompts import REFUSAL, Source, read_prompt

# "AY 2019-20", "tax year 2026-27", "financial year 2014-15", "as on 2017"
YEAR_RE = re.compile(
    r"\b(?:AY|a\.y\.|tax year|financial year|FY|f\.y\.|year)?\s*(\d{4})\b"
)

# Years the corpus can speak to: 1961 Act up to AY 2026-27, 2025 Act from 2026-27.
EARLIEST = 1961
LATEST = 2030  # forwards-looking questions are still answerable from the 2025 Act

REASONS = {
    "low_score": "the closest passages were not relevant enough to answer from",
    "no_section_match": "no section in the corpus matches the terms in the question",
    "out_of_corpus_date": "the tax year in the question is outside the documents I hold",
    "empty_retrieval": "nothing in the corpus matched the question",
}

DETAIL = {
    "low_score": "The closest sections were about a different subject. Rephrasing with "
                 "a section number, or a term the statute actually uses, usually works.",
    "no_section_match": "Try naming the provision (for example “section 80C”) or the head "
                        "of income.",
    "out_of_corpus_date": "The 1961 Act copy is consolidated to Finance Act 2021 and the "
                          "2025 Act applies from tax year 2026-27.",
    "empty_retrieval": "This corpus covers income-tax and GST statute only — not case law, "
                       "state taxes or ITR forms.",
}


@dataclass(slots=True)
class Refusal:
    reason: str
    message: str

    def payload(self) -> dict[str, str]:
        return {"reason": self.reason, "message": self.message}


def _template(reason: str) -> str:
    return read_prompt(REFUSAL).format(reason=REASONS[reason], detail=DETAIL[reason])


def out_of_corpus_year(question: str) -> int | None:
    """The offending year, when the question points outside the corpus's reach."""
    for match in YEAR_RE.finditer(question):
        year = int(match.group(1))
        if year < EARLIEST or year > LATEST:
            return year
    return None


def should_refuse(question: str, sources: list[Source], top_score: float) -> Refusal | None:
    """Return a refusal when the retrieval cannot support an answer, else None."""
    if not sources:
        return Refusal("empty_retrieval", _template("empty_retrieval"))

    year = out_of_corpus_year(question)
    if year is not None:
        return Refusal("out_of_corpus_date", _template("out_of_corpus_date"))

    threshold = get_settings().refusal_score_threshold
    if top_score < threshold:
        return Refusal("low_score", _template("low_score"))

    # A section anchor is what the product promises. If the question names one
    # ("under section 80C") and no source is that section, refuse rather than
    # answer from a neighbouring provision.
    named = re.findall(r"\b(?:section|sec\.?|s\.)\s*(\d{1,3}[A-Z]{0,3})\b", question, re.IGNORECASE)
    if named:
        sections = {(s.section or "").upper() for s in sources}
        if not any(n.upper() in sections for n in named):
            return Refusal("no_section_match", _template("no_section_match"))

    return None
