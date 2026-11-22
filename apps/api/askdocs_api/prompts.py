"""Prompt loading and context assembly.

Prompts are versioned files, not f-strings in code (anti-gaming rule 1 in
`docs/EVAL.md`): a prompt change has to be a reviewable diff, and the version is
recorded on every run so a number can be traced to the text that produced it.

Context assembly is also where "the model cannot cite what it was not given"
becomes true: sources are numbered here, once, and the validator later checks
markers against exactly this list.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
GROUNDED = "grounded-v3"
REFUSAL = "refusal-v1"

# Roughly 4 characters per token for English prose; the budget is enforced on
# characters so assembly never needs the tokenizer (which is the generator's job).
CHARS_PER_TOKEN = 4
MAX_CONTEXT_TOKENS = 3000


@dataclass(slots=True)
class Source:
    """One numbered passage as the model sees it."""

    marker: int
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str | None
    section_title: str | None
    chapter: str | None
    page: int | None
    vintage: str | None
    text: str

    @property
    def header(self) -> str:
        bits = [self.doc_title]
        if self.section:
            bits.append(f"Section {self.section}")
        if self.chapter:
            bits.append(f"Chapter {self.chapter}")
        if self.page:
            bits.append(f"p. {self.page}")
        if self.vintage:
            bits.append(f"as on {self.vintage}")
        return f"[{self.marker}] " + " — ".join(bits)


def read_prompt(name: str) -> str:
    path = PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"prompt missing: {path}")
    return path.read_text(encoding="utf-8")


def prompt_version(name: str) -> str:
    """Short hash of the prompt text - quoted in every eval report."""
    return hashlib.sha256(read_prompt(name).encode("utf-8")).hexdigest()[:8]


def build_sources(candidates: list) -> list[Source]:
    """Number the selected candidates in rerank order, 1-based."""
    return [
        Source(
            marker=i,
            chunk_id=c.chunk_id,
            doc_id=c.doc_id,
            doc_title=c.doc_title,
            section=c.section,
            section_title=c.section_title,
            chapter=c.chapter,
            page=c.page,
            vintage=c.vintage,
            text=c.text.strip(),
        )
        for i, c in enumerate(candidates, start=1)
    ]


def fit_budget(sources: list[Source], budget_tokens: int = MAX_CONTEXT_TOKENS) -> list[Source]:
    """Drop the least relevant sources from the tail until the budget fits.

    Never truncates a source mid-sentence and never drops the head: the first
    source is the one the reranker was most confident about, so if it does not fit
    the answer should be a refusal, not a shortened passage.
    """
    budget_chars = budget_tokens * CHARS_PER_TOKEN
    kept: list[Source] = []
    used = 0
    for source in sources:
        cost = len(source.header) + len(source.text) + 2
        if kept and used + cost > budget_chars:
            break
        kept.append(source)
        used += cost
    return kept


def build_prompt(question: str, sources: list[Source]) -> str:
    """Sources first, question after: a small model reads evidence before rules.

    Measured reason: with the rules-first v1 prompt, qwen2.5:3b answered "I can't
    verify this" for questions whose correct section was already in the context.
    Putting the statute ahead of the instruction and shrinking the rule block made
    the same model use the evidence.
    """
    block = "\n\n".join(f"{s.header}\n{s.text}" for s in sources)
    return read_prompt(GROUNDED).format(question=question.strip(), sources=block)


def source_block(sources: list[Source]) -> str:
    return "\n\n".join(f"{s.header}\n{s.text}" for s in sources)
