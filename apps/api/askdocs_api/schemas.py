"""Response models. Field names match `docs/API.md` exactly - the SSE contract and
the generated TypeScript client both read from here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Scores(BaseModel):
    dense: float | None = None
    lexical: float | None = None
    rrf: float | None = None
    rerank: float | None = None


class Passage(BaseModel):
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
    scores: Scores


class SearchMeta(BaseModel):
    returned: int
    candidates: int
    took_ms: int
    degraded: str | None = None


class SearchResponse(BaseModel):
    data: list[Passage]
    meta: SearchMeta


class SectionResponse(BaseModel):
    doc_id: str
    doc_title: str
    section: str
    section_title: str | None
    chapter: str | None
    page: int | None
    vintage: str | None
    applies_to_ay: str | None
    chunks: list[Passage]
    text: str


class CorpusDocument(BaseModel):
    doc_id: str
    title: str
    doc_type: str
    publisher: str | None
    vintage: str | None
    applies_to_ay: str | None
    pages: int | None
    chunks: int
    sections: int
    sections_unparsed: int | None = None
    sha256: str


class CorpusStats(BaseModel):
    documents: list[CorpusDocument]
    chunks: int
    sections: int
    chars: int
    corpus_hash: str | None = None
    extractor: str | None = None


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: list[dict[str, Any]] | None = Field(default=None)


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, str]
