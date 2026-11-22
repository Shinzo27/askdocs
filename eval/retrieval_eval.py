#!/usr/bin/env python3
"""Retrieval-only evaluation: recall@10, MRR@10 and section hit rate.

No LLM is called, so a run costs zero and can be repeated as often as the index
changes. Three configurations are measured side by side because the README's
claim - "hybrid + rerank beats dense alone" - is a measurement, not an opinion:

    dense            cosine top-50
    lexical          ts_rank_cd top-50
    hybrid           Reciprocal Rank Fusion of the two
    hybrid+rerank    + cross-encoder, section-deduped top-6

    python eval/retrieval_eval.py                  # all four, 25-question subset
    python eval/retrieval_eval.py --mode dense     # one configuration
    python eval/retrieval_eval.py --full            # every question with a section
    python eval/retrieval_eval.py --no-rerank       # skip the cross-encoder

Exit code 1 when recall@10 for the best configuration is below the Week 1 gate
(0.85), so CI can use the script directly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

GOLDEN = ROOT / "eval" / "golden_set.jsonl"
REPORTS = ROOT / "eval" / "reports"
DOCS_EVAL = ROOT / "docs" / "eval"
GATE = 0.85


@dataclass(slots=True)
class Row:
    qid: str
    question: str
    expected: list[tuple[str, str]]
    rank: int | None = None  # rank of the first correct-section chunk (1-based)
    top1: tuple[str, str] | None = None  # section of the best selected passage


@dataclass(slots=True)
class Config:
    name: str
    use_dense: bool
    use_lexical: bool
    use_rerank: bool
    rows: list[Row] = field(default_factory=list)
    ms: list[float] = field(default_factory=list)


def load_questions(full: bool) -> list[dict]:
    questions = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line]
    scored = [q for q in questions if q.get("expected_sections") and q.get("expected_doc")]
    return scored if full else [q for q in scored if q.get("retrieval_subset")]


async def corpus_meta(session) -> dict[str, str]:
    from sqlalchemy import text

    rows = (await session.execute(text("SELECT key, value FROM corpus_meta"))).all()
    return {k: v for k, v in rows}


async def run_config(name: str, questions: list[dict], session, *,
                     use_dense: bool, use_lexical: bool, use_rerank: bool,
                     top_n: int = 10) -> Config:
    from askdocs_api.config import get_settings
    from askdocs_api.retrieval import (
        dedupe_by_section,
        dense_search,
        lexical_search,
        reciprocal_rank_fusion,
        rerank,
        retrieve,
    )

    settings = get_settings()
    config = Config(name=name, use_dense=use_dense, use_lexical=use_lexical, use_rerank=use_rerank)

    for question in questions:
        expected = [(question["expected_doc"], s) for s in question["expected_sections"]]
        started = time.perf_counter()
        if use_rerank and use_dense and use_lexical:
            result = await retrieve(session, question["question"], top_k=settings.rerank_top_k)
            ranked = result.selected
            # recall@10 is measured over the reranked candidate list, not the six
            # deduped passages that go into the prompt - otherwise the metric is
            # quietly recall@6 and the gate comparison is unfair across configs.
            seen = result.reranked
        else:
            dense = await dense_search(session, question["question"], settings.dense_top_k, None) \
                if use_dense else []
            lexical = await lexical_search(session, question["question"], settings.lexical_top_k, None) \
                if use_lexical else []
            fused = reciprocal_rank_fusion(dense, lexical, k=settings.rrf_k)
            if use_rerank:
                ordered = rerank(question["question"], fused[: settings.rerank_candidates])
                ranked = dedupe_by_section(ordered, settings.rerank_top_k)
                seen = ordered
            else:
                ranked = fused
                seen = fused
        config.ms.append((time.perf_counter() - started) * 1000)

        rank = None
        for i, candidate in enumerate(seen[:top_n], start=1):
            if (candidate.doc_id, candidate.section) in expected:
                rank = i
                break
        top1 = (ranked[0].doc_id, ranked[0].section) if ranked else None
        config.rows.append(
            Row(
                qid=question["id"],
                question=question["question"],
                expected=expected,
                rank=rank,
                top1=top1,
            )
        )
    return config


def summarise(config: Config) -> dict[str, float]:
    n = len(config.rows) or 1
    recall = sum(1 for r in config.rows if r.rank is not None) / n
    mrr = sum(1.0 / r.rank for r in config.rows if r.rank) / n
    hit1 = sum(1 for r in config.rows if r.top1 in r.expected) / n
    return {
        "recall@10": round(recall, 4),
        "mrr@10": round(mrr, 4),
        "section_hit_rate@1": round(hit1, 4),
        "p50_ms": round(statistics.median(config.ms), 1) if config.ms else 0.0,
        "p95_ms": round(sorted(config.ms)[int(len(config.ms) * 0.95) - 1], 1) if config.ms else 0.0,
    }


async def main_async(args: argparse.Namespace) -> int:
    from askdocs_api import db
    from askdocs_api.embeddings import model_name

    questions = load_questions(args.full)
    if not questions:
        sys.exit("no scorable questions found in eval/golden_set.jsonl")

    configs = [
        Config("dense", True, False, False),
        Config("lexical", False, True, False),
        Config("hybrid", True, True, False),
        Config("hybrid+rerank", True, True, not args.no_rerank),
    ]
    if args.mode != "all":
        configs = [c for c in configs if c.name == args.mode]

    print(f"retrieval eval - {len(questions)} questions, "
          f"{'full set' if args.full else 'Week 1 subset'}")
    results: list[Config] = []
    async with db.session_factory()() as session:
        meta = await corpus_meta(session)
        for config in configs:
            started = time.perf_counter()
            results = [*results, await run_config(
                config.name, questions, session,
                use_dense=config.use_dense, use_lexical=config.use_lexical, use_rerank=config.use_rerank,
            )]
            print(f"  {config.name:14s} done in {time.perf_counter() - started:.1f}s")

    rows = [(c, summarise(c)) for c in results]
    ts = datetime.now(UTC)
    stamp = ts.strftime("%Y-%m-%dT%H-%M")
    best = max(rows, key=lambda pair: pair[1]["recall@10"])
    payload = {
        "run": {"timestamp": ts.isoformat(), "questions": len(questions), "full": args.full},
        "corpus": {"hash": meta.get("corpus_hash"), "extractor": meta.get("extractor"),
                   "embedding_model": model_name()},
        "configs": [
            {"name": c.name, "metrics": metrics,
             "questions": [
                 {"id": r.qid, "question": r.question, "expected": r.expected,
                  "first_correct_rank": r.rank, "top1": r.top1}
                 for r in c.rows
             ]}
            for c, metrics in rows
        ],
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{stamp}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    table = render_markdown(rows, meta, len(questions), args.full)
    (REPORTS / f"{stamp}.md").write_text(table, encoding="utf-8")
    DOCS_EVAL.mkdir(parents=True, exist_ok=True)
    (DOCS_EVAL / "latest.md").write_text(table, encoding="utf-8")
    if args.full:
        (DOCS_EVAL / "retrieval-w1.md").write_text(table, encoding="utf-8")

    print(table)
    await db.dispose()
    if best[1]["recall@10"] < GATE:
        print(f"GATE FAILED: recall@10 {best[1]['recall@10']} < {GATE}", file=sys.stderr)
        return 1
    return 0


def render_markdown(rows: list[tuple[Config, dict[str, float]]], meta: dict[str, str],
                    n: int, full: bool) -> str:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        f"## Retrieval run {stamp}",
        "",
        f"- questions: **{n}** ({'full set' if full else 'Week 1 subset'})",
        (
            f"- corpus_hash: `{(meta.get('corpus_hash') or 'unknown')[:12]}`"
            f" · extractor {meta.get('extractor') or 'unknown'}"
        ),
        "- generation: none (retrieval only, zero LLM cost)",
        "",
        "| Configuration | recall@10 | MRR@10 | section hit@1 | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|",
    ]
    for config, metrics in rows:
        out.append(
            f"| {config.name} | {metrics['recall@10']:.2f} | {metrics['mrr@10']:.2f} | "
            f"{metrics['section_hit_rate@1']:.2f} | {metrics['p50_ms']:.0f} | {metrics['p95_ms']:.0f} |"
        )
    misses = [
        (c.name, r) for c, _ in rows if c.name == "hybrid+rerank" for r in c.rows if r.rank is None
    ]
    out.append("")
    if misses:
        out.append("**Misses (hybrid+rerank):** " + ", ".join(f"{r.qid}" for _, r in misses))
    else:
        out.append("**No misses:** a chunk from every expected section appears in the top-10.")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="all",
                    choices=["all", "dense", "lexical", "hybrid", "hybrid+rerank"])
    ap.add_argument("--full", action="store_true", help="score every question with a section")
    ap.add_argument("--no-rerank", action="store_true", help="skip the cross-encoder (fast)")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
