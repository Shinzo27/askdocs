"""The ask pipeline: retrieval → refusal gate → generation → validation → events.

One function, `answer`, yields the SSE events `docs/API.md` specifies, in that
order. Everything that can be decided without a model is decided first: an
unanswerable question is refused in ~200 ms with no generation call, which is
cheaper, faster and more honest than a fluent miss (ADR-005).
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from askdocs_api import generators, prompts
from askdocs_api.citations import cited_sources, validate
from askdocs_api.config import get_settings
from askdocs_api.refusal import should_refuse
from askdocs_api.retrieval import retrieve

MAX_QUESTION = 500

# The refusal sentence the prompt asks for, tolerated with or without the colon part.
REFUSAL_RE = re.compile(r"i can'?t verify this from the documents i (?:have|hold)", re.IGNORECASE)


def is_model_refusal(text: str) -> bool:
    """True when the model declined instead of answering."""
    stripped = text.strip()
    return bool(REFUSAL_RE.search(stripped)) and len(stripped) < 400


def sse(event: str, data: dict[str, Any]) -> dict[str, str]:
    """One SSE frame in the shape sse-starlette expects."""
    import json

    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


async def answer(
    session: AsyncSession,
    question: str,
    *,
    request_id: str,
    conversation_id: uuid.UUID | None = None,
    generator_provider: str | None = None,
) -> AsyncIterator[dict[str, str]]:
    """Yield `retrieval`, `token`*, `citation`*, `usage`, `done` — or `error`."""
    started = time.perf_counter()
    question = question.strip()[:MAX_QUESTION]

    try:
        result = await retrieve(session, question)
    except Exception as exc:
        yield sse("error", {"code": "retrieval_failed", "message": str(exc)[:200],
                            "request_id": request_id, "retryable": True})
        return

    sources = prompts.fit_budget(prompts.build_sources(result.selected))
    top_score = result.top_score

    yield sse("retrieval", {
        "request_id": request_id,
        "candidates": len(result.candidates),
        "fused": result.fused_count,
        "reranked": len(result.reranked),
        "top_score": round(top_score, 4),
        "sections": [s.section for s in sources if s.section],
        "latency_ms": {"retrieve": result.retrieval_ms, "rerank": result.rerank_ms},
    })

    refusal = should_refuse(question, sources, top_score)
    if refusal is not None:
        message_id = uuid.uuid4().hex[:8]
        yield sse("token", {"text": refusal.message})
        yield sse("usage", {
            "prompt_tokens": 0, "completion_tokens": 0, "provider": "none", "model": "none",
            "cost_inr": 0.0,
            "latency_ms": {"retrieve": result.retrieval_ms, "rerank": result.rerank_ms,
                           "first_token": int((time.perf_counter() - started) * 1000),
                           "total": int((time.perf_counter() - started) * 1000)},
        })
        yield sse("done", {"message_id": message_id, "citation_valid": True,
                           "refused": True, **refusal.payload()})
        return

    prompt = prompts.build_prompt(question, sources)
    generator = (
        _generator_for(generator_provider) if generator_provider else generators.build_generator()
    )

    chunks: list[str] = []
    first_token_ms = 0
    try:
        async for delta in generator.stream(prompt):
            if not chunks:
                first_token_ms = int((time.perf_counter() - started) * 1000)
            chunks.append(delta)
            yield sse("token", {"text": delta})
    except Exception as exc:
        yield sse("error", {"code": "provider_unavailable", "message": str(exc)[:200],
                            "request_id": request_id, "retryable": True})
        return

    raw = "".join(chunks).strip()

    # A model may refuse on its own when the evidence is thin. That is a correct
    # outcome, not a citation failure: record it as a refusal with its own reason so
    # refusal correctness is measured on the model's behaviour too, not just on our
    # score gate.
    if is_model_refusal(raw):
        total_ms = int((time.perf_counter() - started) * 1000)
        yield sse("usage", {
            "prompt_tokens": generator.usage.prompt_tokens,
            "completion_tokens": generator.usage.completion_tokens,
            "provider": generator.usage.provider, "model": generator.usage.model,
            "cost_inr": generator.usage.cost_inr,
            "latency_ms": {"retrieve": result.retrieval_ms, "rerank": result.rerank_ms,
                           "first_token": first_token_ms, "total": total_ms},
        })
        yield sse("done", {"message_id": uuid.uuid4().hex[:8], "citation_valid": True,
                           "refused": True, "reason": "model_refused", "message": raw})
        return

    check = validate(raw, sources)
    final_text = check.text or raw
    used = cited_sources(final_text, sources)

    for source in used:
        yield sse("citation", {
            "marker": source.marker,
            "doc_id": source.doc_id,
            "section": source.section,
            "section_title": source.section_title,
            "chapter": source.chapter,
            "page": source.page,
            "vintage": source.vintage,
            "rerank_score": round(
                next((c.scores.get("rerank", 0.0) for c in result.selected
                      if c.chunk_id == source.chunk_id), 0.0), 4),
        })

    usage = generator.usage
    total_ms = int((time.perf_counter() - started) * 1000)
    yield sse("usage", {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "provider": usage.provider,
        "model": usage.model,
        "cost_inr": usage.cost_inr,
        "latency_ms": {
            "retrieve": result.retrieval_ms,
            "rerank": result.rerank_ms,
            "first_token": first_token_ms,
            "total": total_ms,
        },
    })

    yield sse("done", {
        "message_id": uuid.uuid4().hex[:8],
        "citation_valid": check.valid,
        "refused": False,
        "stripped_sentences": check.stripped_sentences,
        "reason": check.reason,
    })


def _generator_for(provider: str) -> generators.Generator:
    settings = get_settings()
    if provider == "echo":
        return generators.EchoGenerator()
    if provider == settings.generator_provider:
        return generators.build_generator()
    raise ValueError(f"unknown provider: {provider}")
