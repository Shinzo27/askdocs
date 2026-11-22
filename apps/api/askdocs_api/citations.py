"""Citation validation: turn `[n]` markers into a checked fact, not a hope.

ADR-006: a prompt instruction is a hope, validation is a check. After generation
every marker is resolved against the sources that were actually supplied; a marker
outside that list fails the message, and `citation_valid` is stored so the metric
becomes a queryable fact about the corpus rather than a claim about a prompt.

The strict mode strips unsupported sentences before they reach the reader. That is
deliberately aggressive: in tax, a sentence with a confident number and no citation
is worse than a shorter answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from askdocs_api.prompts import Source

MARKER_RE = re.compile(r"\[(\d{1,2})\]")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+")

# Sentences that are allowed to carry no marker: transitions and the refusal line.
NEUTRAL_RE = re.compile(
    r"^(Sources?:|See |Note that the corpus|I can't verify this from the documents I have)",
    re.IGNORECASE,
)


@dataclass(slots=True)
class CitationCheck:
    valid: bool
    markers: list[int] = field(default_factory=list)
    unsupported: list[int] = field(default_factory=list)  # markers with no source
    text: str = ""
    stripped_sentences: int = 0
    reason: str | None = None

    @property
    def cited_sources(self) -> list[Source]:  # filled by the caller in order
        return []


def _sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def validate(answer: str, sources: list[Source], *, strict: bool = True) -> CitationCheck:
    """Resolve markers against the supplied sources and enforce the contract.

    `strict` drops sentences that make a claim without a marker. It never invents
    a citation and never rewrites a claim - it only removes unsupported text, so
    the remaining answer is a subset of what the model said.
    """
    if not answer.strip():
        return CitationCheck(valid=False, reason="empty_answer")

    known = {s.marker for s in sources}
    markers = [int(m) for m in MARKER_RE.findall(answer)]
    unsupported = sorted({m for m in markers if m not in known})

    if not markers:
        return CitationCheck(valid=False, markers=[], unsupported=[], text=answer,
                             reason="no_markers")
    if unsupported:
        return CitationCheck(valid=False, markers=sorted(set(markers)),
                             unsupported=unsupported, text=answer,
                             reason="marker_outside_context")

    if not strict:
        return CitationCheck(valid=True, markers=sorted(set(markers)), text=answer)

    kept: list[str] = []
    stripped = 0
    for sentence in _sentences(answer):
        has_marker = bool(MARKER_RE.search(sentence))
        if has_marker or NEUTRAL_RE.match(sentence) or len(sentence) < 25:
            kept.append(sentence)
        else:
            stripped += 1
    text = " ".join(kept).strip()

    # Unreachable in practice: reaching here means a marker existed, so at least
    # one sentence survived. Kept as a guard rather than a silent empty answer.
    if not text:  # pragma: no cover
        return CitationCheck(valid=False, markers=sorted(set(markers)), text=answer,
                             stripped_sentences=stripped, reason="all_claims_uncited")

    return CitationCheck(
        valid=True, markers=sorted(set(markers)), text=text, stripped_sentences=stripped
    )


def cited_sources(answer: str, sources: list[Source]) -> list[Source]:
    """Sources actually referenced, in ascending marker order."""
    used = {int(m) for m in MARKER_RE.findall(answer)}
    return [s for s in sources if s.marker in used]
