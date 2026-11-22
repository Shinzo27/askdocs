"""FastAPI application: retrieval endpoints only (Week 1).

`/ask` (streaming generation) is Week 2; until it exists this service is honest
about being a retriever, and `/search` is the surface the eval harness measures.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from askdocs_api import db
from askdocs_api.config import get_settings
from askdocs_api.models import Chunk, Document
from askdocs_api.retrieval import retrieve
from askdocs_api.schemas import (
    CorpusDocument,
    CorpusStats,
    HealthResponse,
    Passage,
    Scores,
    SearchMeta,
    SearchResponse,
    SectionResponse,
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await db.dispose()


def _passage(candidate: Any) -> Passage:
    return Passage(
        chunk_id=candidate.chunk_id,
        doc_id=candidate.doc_id,
        doc_title=candidate.doc_title,
        doc_type=candidate.doc_type,
        vintage=candidate.vintage,
        applies_to_ay=candidate.applies_to_ay,
        section=candidate.section,
        section_title=candidate.section_title,
        chapter=candidate.chapter,
        page=candidate.page,
        text=candidate.text,
        scores=Scores(**{k: v for k, v in candidate.scores.items()
                         if k in {"dense", "lexical", "rrf", "rerank"}}),
    )


async def _corpus_hash(session: AsyncSession) -> str | None:
    """Stored by the loader; the number every eval report quotes."""
    row = (
        await session.execute(
            text("SELECT value FROM corpus_meta WHERE key = 'corpus_hash'")
        )
    ).first()
    return row[0] if row else None


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AskDocs API",
        version="0.1.0",
        description="Section-anchored hybrid retrieval over Indian tax statute. "
        "Informational only, not legal advice.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.web_origin],
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def request_id(request: Request, call_next: Any) -> Any:
        request.state.request_id = (
            request.headers.get("X-Request-Id") or f"r-{uuid.uuid4().hex[:8]}"
        )
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = exc.detail if isinstance(exc.detail, str) else "error"
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": code, "message": str(exc.detail),
                               "request_id": getattr(request.state, "request_id", None)}},
        )

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok", checks={"process": "alive"})

    @app.get("/readyz", response_model=HealthResponse)
    async def readyz(session: AsyncSession = Depends(db.get_session)) -> HealthResponse:
        checks: dict[str, str] = {}
        try:
            await session.execute(text("SELECT 1"))
            checks["db"] = "ok"
        except Exception as exc:
            checks["db"] = f"error: {type(exc).__name__}"
        status = "ok" if checks["db"] == "ok" else "degraded"
        return HealthResponse(status=status, checks=checks)

    @app.get("/api/v1/search", response_model=SearchResponse)
    async def search(
        q: str = Query(min_length=3, max_length=500),
        limit: int = Query(default=6, ge=1, le=20),
        doc_scope: list[str] | None = Query(default=None),
        debug: int = Query(default=0, ge=0, le=1),
        session: AsyncSession = Depends(db.get_session),
    ) -> SearchResponse:
        started = time.perf_counter()
        result = await retrieve(session, q, doc_scope=doc_scope, top_k=limit)
        took_ms = int((time.perf_counter() - started) * 1000)
        passages = [_passage(c) for c in result.selected]
        if not debug:
            for passage in passages:
                if passage.scores.rerank is None:
                    passage.scores = Scores()
        return SearchResponse(
            data=passages,
            meta=SearchMeta(
                returned=len(passages),
                candidates=result.fused_count,
                took_ms=took_ms,
                degraded=result.degraded,
            ),
        )

    @app.get("/api/v1/sections/{doc_id}/{section}", response_model=SectionResponse)
    async def section(
        doc_id: str,
        section: str,
        session: AsyncSession = Depends(db.get_session),
    ) -> SectionResponse:
        rows = (
            await session.execute(
                select(Chunk)
                .where(Chunk.doc_id == doc_id, Chunk.section == section)
                .order_by(Chunk.chunk_index)
            )
        ).scalars().all()
        if not rows:
            raise HTTPException(status_code=404, detail="not_found")
        document = await session.get(Document, doc_id)
        from askdocs_api.retrieval import Candidate  # local import keeps models independent

        passages = [
            _passage(
                Candidate(
                    chunk_id=row.id,
                    doc_id=row.doc_id,
                    doc_title=document.title if document else row.doc_id,
                    doc_type=document.doc_type if document else "",
                    vintage=document.vintage if document else None,
                    applies_to_ay=document.applies_to_ay if document else None,
                    section=row.section,
                    section_title=row.section_title,
                    chapter=row.chapter,
                    page=row.page,
                    text=row.text,
                    chars=row.chars,
                )
            )
            for row in rows
        ]
        return SectionResponse(
            doc_id=doc_id,
            doc_title=document.title if document else doc_id,
            section=section,
            section_title=rows[0].section_title,
            chapter=rows[0].chapter,
            page=rows[0].page,
            vintage=document.vintage if document else None,
            applies_to_ay=document.applies_to_ay if document else None,
            chunks=passages,
            text="\n\n".join(row.text for row in rows),
        )

    @app.get("/api/v1/corpus/stats", response_model=CorpusStats)
    async def corpus_stats(session: AsyncSession = Depends(db.get_session)) -> CorpusStats:
        counts = dict(
            (
                await session.execute(
                    select(Chunk.doc_id, func.count()).group_by(Chunk.doc_id)
                )
            ).all()
        )
        sections = dict(
            (
                await session.execute(
                    select(Chunk.doc_id, func.count(func.distinct(Chunk.section)))
                    .where(Chunk.section.is_not(None))
                    .group_by(Chunk.doc_id)
                )
            ).all()
        )
        documents = (
            (await session.execute(select(Document).order_by(Document.doc_id))).scalars().all()
        )
        total_chars = (
            await session.execute(select(func.coalesce(func.sum(Chunk.chars), 0)))
        ).scalar_one()
        total_sections = (
            await session.execute(
                select(func.count(func.distinct(func.concat(Chunk.doc_id, ":", Chunk.section))))
                .where(Chunk.section.is_not(None))
            )
        ).scalar_one()
        unparsed = dict(
            (
                await session.execute(
                    text("SELECT doc_id, sections_unparsed FROM documents")
                )
            ).all()
        )
        return CorpusStats(
            documents=[
                CorpusDocument(
                    doc_id=d.doc_id,
                    title=d.title,
                    doc_type=d.doc_type,
                    publisher=d.publisher,
                    vintage=d.vintage,
                    applies_to_ay=d.applies_to_ay,
                    pages=d.pages,
                    chunks=int(counts.get(d.doc_id, 0)),
                    sections=int(sections.get(d.doc_id, 0)),
                    sections_unparsed=unparsed.get(d.doc_id),
                    sha256=d.sha256,
                )
                for d in documents
            ],
            chunks=int(sum(counts.values())),
            sections=int(total_sections),
            chars=int(total_chars),
            corpus_hash=await _corpus_hash(session),
            extractor=None,
        )

    return app


app = create_app()
