"""Hybrid retrieval: dense ∥ full-text → Reciprocal Rank Fusion → rerank → dedupe.

Why each step exists (ADR-003):

* dense alone misses exact statutory phrasing ("notwithstanding anything
  contained in"), because the words carry little semantic weight;
* full-text alone misses paraphrase ("deduction for my kid's school fees");
* RRF is rank-based, so cosine similarity and `ts_rank_cd` never have to be
  calibrated against each other - pretending those two numbers are comparable is
  the bug this design avoids;
* the cross-encoder sees query and passage together, which is where most of the
  accuracy on short statute passages comes from;
* two chunks of the same section would otherwise eat the whole prompt, so the
  final selection is section-aware.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from askdocs_api.config import get_settings
from askdocs_api.embeddings import embed_query

_COLUMNS = """c.id, c.doc_id, c.section, c.section_title, c.chapter, c.page,
           c.chunk_index, c.text, c.chars,
           d.title AS doc_title, d.vintage, d.applies_to_ay, d.doc_type"""

_SELECT = f"""
    SELECT {_COLUMNS}
      FROM chunks c
      JOIN documents d ON d.doc_id = c.doc_id
"""


@dataclass(slots=True)
class Candidate:
    """One passage on its way from the database to the prompt."""

    chunk_id: str
    doc_id: str
    doc_title: str
    doc_type: str
    vintage: str | None
    applies_to_ay: str | None
    section: str | None
    section_title: str | None
    chapter: str | None
    page: int | None
    text: str
    chars: int
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """`doc · section · chapter · page · vintage` - the citation's address."""
        bits = [self.doc_title]
        if self.section:
            bits.append(f"Section {self.section}")
        if self.chapter:
            bits.append(f"Chapter {self.chapter}")
        if self.page:
            bits.append(f"p. {self.page}")
        if self.vintage:
            bits.append(f"(as on {self.vintage})")
        return " — ".join(bits)


@dataclass(slots=True)
class RetrievalResult:
    candidates: list[Candidate]  # fused, pre-rerank (for the debug view)
    reranked: list[Candidate]  # cross-encoder order, pre-dedupe (for recall@10)
    selected: list[Candidate]  # what goes into the prompt
    fused_count: int
    retrieval_ms: int
    rerank_ms: int
    degraded: str | None = None

    @property
    def top_score(self) -> float:
        return self.selected[0].scores.get("rerank", 0.0) if self.selected else 0.0


def _row_to_candidate(row: Any) -> Candidate:
    return Candidate(
        chunk_id=row.id,
        doc_id=row.doc_id,
        doc_title=row.doc_title,
        doc_type=row.doc_type,
        vintage=row.vintage,
        applies_to_ay=row.applies_to_ay,
        section=row.section,
        section_title=row.section_title,
        chapter=row.chapter,
        page=row.page,
        text=row.text,
        chars=row.chars,
    )


def _scope_clause(doc_scope: list[str] | None, alias: str = "c") -> tuple[str, dict[str, Any]]:
    if not doc_scope:
        return "", {}
    return f" AND {alias}.doc_id = ANY(:doc_scope)", {"doc_scope": doc_scope}



# Which instrument a question is about, when it says so. Three of the four Week 1
# misses were the right section number inside the wrong document: both Acts are in
# one index and a question that does not name its vintage leaves the retriever to
# guess. Reading the instrument out of the question is the cheapest half of that
# fix and it is measurable.
_ACT_1961_RE = re.compile(r"\b(1961|income[- ]tax act,?\s*1961)\b", re.IGNORECASE)
_ACT_2025_RE = re.compile(r"\b(2025|income[- ]tax act,?\s*2025)\b", re.IGNORECASE)
_GST_RE = re.compile(r"\b(cgst|gst|goods and services tax)\b", re.IGNORECASE)


def infer_doc_scope(question: str) -> list[str] | None:
    """Documents the question names, or None to search everything."""
    scopes: list[str] = []
    if _ACT_1961_RE.search(question):
        scopes.append("it-act-1961")
    if _ACT_2025_RE.search(question):
        scopes.extend(["it-act-2025", "it-rules-2026"])
    if _GST_RE.search(question):
        scopes.extend(["cgst-act-2017", "cgst-rules-2017"])
    return list(dict.fromkeys(scopes)) or None


async def dense_search(
    session: AsyncSession, query: str, limit: int, doc_scope: list[str] | None
) -> list[Candidate]:
    vector = embed_query(query)
    literal = "[" + ",".join(f"{v:.6f}" for v in vector.tolist()) + "]"
    clause, params = _scope_clause(doc_scope)
    sql = f"""
        SELECT {_COLUMNS},
               1 - (c.embedding <=> CAST(:vector AS vector)) AS dense_sim
          FROM chunks c
          JOIN documents d ON d.doc_id = c.doc_id
         WHERE c.embedding IS NOT NULL AND NOT c.omitted{clause}
         ORDER BY c.embedding <=> CAST(:vector AS vector)
         LIMIT :limit
    """
    rows = (await session.execute(text(sql), {"vector": literal, "limit": limit, **params})).all()
    found = []
    for rank, row in enumerate(rows, start=1):
        candidate = _row_to_candidate(row)
        candidate.scores["dense"] = float(row._mapping.get("dense_sim") or 0.0)
        candidate.scores["dense_rank"] = float(rank)
        found.append(candidate)
    return found


async def lexical_search(
    session: AsyncSession,
    query: str,
    limit: int,
    doc_scope: list[str] | None,
    terms: int | None = None,
) -> list[Candidate]:
    """Full-text candidates ranked by inverse document frequency.

    Three measured failures shaped this, in order:

    * `websearch_to_tsquery` ANDs every term, so a natural-language question
      matched almost nothing (recall@10 0.08);
    * a plain OR ranked with `ts_rank_cd`, which knows term frequency and proximity
      but not rarity - "deduct" appears in 1,653 chunks, "80C" in 12, so the common
      stem won (recall@10 0.16);
    * keeping only the rarest terms was worse still (0.32 at best): rarity is not
      informativeness, and "regardless" is rarer than "registration".

    So every lexeme is kept and each contributes `1/(1+ndoc)` when the chunk
    matches it - a document-frequency weight computed from `lexeme_stats`, which
    `load_db.py` rebuilds from `ts_stat` on load. A chunk that matches "80C" gains
    more than one that only says "deduction" seven times. This is a lexical
    relevance model that knows what the corpus is about, which is what makes the
    second retriever worth its latency next to the dense one.
    """
    clause, params = _scope_clause(doc_scope)
    lexical_terms = terms or get_settings().lexical_terms
    sql = f"""
        WITH qlex AS (
            SELECT DISTINCT lexeme
              FROM unnest(to_tsvector('english', :q_text))
             WHERE length(lexeme) > 1
        ), weighted AS (
            SELECT q.lexeme, 1.0 / (1 + coalesce(s.ndoc, 1)) AS weight
              FROM qlex q
              LEFT JOIN lexeme_stats s ON s.lexeme = q.lexeme
             ORDER BY weight DESC
             LIMIT :terms
        ), tsq AS (
            SELECT to_tsquery('english',
                       array_to_string(ARRAY(SELECT lexeme FROM weighted), ' | ')) AS q
        )
        SELECT {_COLUMNS},
               sum(w.weight) AS lexical
          FROM chunks c
          JOIN documents d ON d.doc_id = c.doc_id
          CROSS JOIN tsq
          JOIN weighted w ON c.tsv @@ to_tsquery('english', w.lexeme)
         WHERE c.tsv @@ tsq.q AND NOT c.omitted{clause}
         GROUP BY c.id, d.doc_id
         ORDER BY lexical DESC
         LIMIT :limit
    """
    try:
        rows = (await session.execute(
            text(sql), {"q_text": query, "limit": limit, "terms": lexical_terms, **params}
        )).all()
    except Exception:
        return []
    found = []
    for rank, row in enumerate(rows, start=1):
        candidate = _row_to_candidate(row)
        candidate.scores["lexical"] = float(row._mapping.get("lexical") or 0.0)
        candidate.scores["lexical_rank"] = float(rank)
        found.append(candidate)
    return found


def reciprocal_rank_fusion(
    dense: list[Candidate], lexical: list[Candidate], k: int = 60
) -> list[Candidate]:
    """RRF: score = Σ 1/(k + rank), rank starting at 1 in each list."""
    merged: dict[str, Candidate] = {}
    for listing in (dense, lexical):
        for rank, candidate in enumerate(listing, start=1):
            existing = merged.get(candidate.chunk_id)
            if existing is None:
                candidate.scores["rrf"] = 1.0 / (k + rank)
                merged[candidate.chunk_id] = candidate
            else:
                existing.scores["rrf"] = existing.scores.get("rrf", 0.0) + 1.0 / (k + rank)
                for name in ("dense", "lexical", "dense_rank", "lexical_rank"):
                    if name in candidate.scores:
                        existing.scores.setdefault(name, candidate.scores[name])
    return sorted(merged.values(), key=lambda c: c.scores["rrf"], reverse=True)


_reranker: Any = None


def _cross_encoder() -> Any:
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        _reranker = CrossEncoder(get_settings().rerank_model, device="cpu")
    return _reranker


def rerank_input(candidate: Candidate) -> str:
    """What the cross-encoder sees: the citation address, then the passage.

    Feeding raw chunk text scored worse than the dense baseline on questions that
    name a section ("...under section 80C..."), because a chunk body often never
    repeats its own number. Prefixing `Section · title` gives the reranker the same
    handle the question uses - the section is the citation unit, so it belongs in
    the model's input as well as in the answer.
    """
    bits = []
    if candidate.section:
        bits.append(f"Section {candidate.section}")
    if candidate.section_title:
        bits.append(candidate.section_title)
    if candidate.doc_title:
        bits.append(f"({candidate.doc_title})")
    return (" — ".join(bits) + ": " + candidate.text) if bits else candidate.text


def rerank(query: str, candidates: list[Candidate]) -> list[Candidate]:
    """Cross-encoder score for (query, passage); returns a new sorted list."""
    if not candidates:
        return []
    pairs = [(query, rerank_input(c)) for c in candidates]
    scores = _cross_encoder().predict(pairs, batch_size=32, show_progress_bar=False)
    for candidate, score in zip(candidates, scores, strict=True):
        candidate.scores["rerank"] = float(score)
    return sorted(candidates, key=lambda c: c.scores["rerank"], reverse=True)


def dedupe_by_section(
    candidates: list[Candidate], top_k: int, per_section: int = 1
) -> list[Candidate]:
    """Take the best passage per section first, then fill up to `top_k`.

    A second pass allows a second chunk from a section (cap 2) so a genuinely
    multi-paragraph provision can still answer, without one section taking the
    whole context window.
    """
    chosen: list[Candidate] = []
    used: dict[tuple[str, str | None], int] = {}

    for candidate in candidates:
        key = (candidate.doc_id, candidate.section)
        if used.get(key, 0) < per_section:
            chosen.append(candidate)
            used[key] = used.get(key, 0) + 1
        if len(chosen) == top_k:
            return chosen

    if len(chosen) < top_k:
        for candidate in candidates:
            if candidate in chosen:
                continue
            key = (candidate.doc_id, candidate.section)
            if used.get(key, 0) < 2:
                chosen.append(candidate)
                used[key] = used.get(key, 0) + 1
            if len(chosen) == top_k:
                break
    return chosen


async def retrieve(
    session: AsyncSession,
    query: str,
    *,
    doc_scope: list[str] | None = None,
    top_k: int | None = None,
    use_dense: bool = True,
    use_lexical: bool = True,
    use_rerank: bool = True,
) -> RetrievalResult:
    """Full pipeline. `use_*` flags exist for the Week 1 ablation, not tuning."""
    settings = get_settings()
    top_k = top_k or settings.rerank_top_k
    if doc_scope is None:
        doc_scope = infer_doc_scope(query)
    started = time.perf_counter()

    dense = (
        await dense_search(session, query, settings.dense_top_k, doc_scope) if use_dense else []
    )
    lexical = (
        await lexical_search(
            session, query, settings.lexical_top_k, doc_scope, settings.lexical_terms
        )
        if use_lexical
        else []
    )
    retrieval_ms = int((time.perf_counter() - started) * 1000)

    fused = reciprocal_rank_fusion(dense, lexical, k=settings.rrf_k)
    rerank_started = time.perf_counter()
    degraded = None
    if use_rerank:
        try:
            ordered = rerank(query, fused[: settings.rerank_candidates])
        except Exception:
            ordered = fused
            degraded = "rerank"
    else:
        ordered = fused
    rerank_ms = int((time.perf_counter() - rerank_started) * 1000)

    return RetrievalResult(
        candidates=fused,
        reranked=ordered,
        selected=dedupe_by_section(ordered, top_k),
        fused_count=len(fused),
        retrieval_ms=retrieval_ms,
        rerank_ms=rerank_ms,
        degraded=degraded,
    )
