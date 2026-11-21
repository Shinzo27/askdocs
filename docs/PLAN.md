# AskDocs — Four-Week Delivery Plan

**Goal:** a deployed, evaluated tax-law assistant where every answer is traceable to a statute section and a PDF page, and where "I don't know" is a first-class answer.

**Window:** Mon 23 Nov → Sun 20 Dec 2026 (4 weeks, 1 developer).
**Stack:** Next.js 16 · FastAPI · Postgres 16 + pgvector · bge-small + MiniLM reranker · Ollama (default) with OpenAI/Gemini adapters.

Layer tags used below: `[UI]` `[API]` `[RAG]` `[DB]` `[DATA]` `[EVAL]` `[INFRA]` `[DOCS]` — every week touches at least five, so no layer is discovered in the last week.

---

## Definition of done (v1)

1. A stranger opens the URL, asks a tax question, gets a streamed answer whose every claim carries `[n]`.
2. Clicking `[n]` opens the exact section, with document title, vintage and page number, and a link into the PDF at that page.
3. A question outside the corpus is refused with a reason, not answered.
4. `make eval` prints citation accuracy, fact recall, refusal correctness, p95 latency and cost per query.
5. CI blocks a PR that regresses citation accuracy by more than 3 points.
6. `README.md` shows measured numbers, not adjectives.

---

## Week map

| Week | Dates | Theme | One-line ship |
|---|---|---|---|
| **1** | 23–29 Nov | Ground truth first | Corpus v2 + pgvector + hybrid retrieval, measured on 25 questions |
| **2** | 30 Nov – 6 Dec | Answers with a spine | Grounded generation, citation validation, refusal, streaming API + chat UI |
| **3** | 7–13 Dec | Product surface | Citation viewer, history, feedback, eval dashboard, rate limiting |
| **4** | 14–20 Dec | Harden and ship | Deployed, load-tested, CI-gated, documented with real numbers |

Retrieval before generation is deliberate: no prompt engineering survives a bad retriever, and every later number depends on the corpus being right.

---

## Week 1 · Ground truth first (23–29 Nov)

**Corpus status: complete.** Both Acts and both rule sets are ingested and measured (11,080 chunks, 1,907 document/section pairs) by pulling the blocked official PDFs through Wayback snapshots. What remains in this week is the machinery *on top of* the corpus.

- `[DATA]` Corpus v2 is in place; the remaining ingestion work is the **CBDT circular drop** (`data/raw/circulars/`) if you can fetch them, plus a `--verify` mode that re-checks SHA-256 prefixes and page counts against `data/sources.json`.
- `[DATA]` `scripts/embed.py` — batched bge-small encoding, idempotent by content hash, writes an embedding manifest (model, dimension, chunk count, hash) so a model change is detected instead of silently mixing vectors.
- `[DB]` Alembic schema: `documents`, `chunks` (`vector(384)` + generated `tsvector` + GIN), `conversations`, `messages`, `citations`, `query_log`; loader that streams `chunks.jsonl` into Postgres.
- `[RAG]` Hybrid retrieval: dense top-50 ∥ full-text top-50 → **Reciprocal Rank Fusion** → cross-encoder rerank → section-level dedupe → top-6. `GET /api/v1/search?q=` returns scored passages with section, chapter, page, vintage and `?debug=1` score breakdown.
- `[EVAL]` `eval/retrieval_eval.py` over a 25-question retrieval subset drawn from **both** Acts; report **recall@10, MRR, section hit rate** for dense-only vs BM25-only vs hybrid+rerank.
- `[INFRA]` `docker compose up` (api, db, ollama), `Makefile` targets, pytest skeleton, pre-commit hooks, and a regression test that asserts the four original documents keep their exact chunk counts (3,868 / 578 / 863 / 1,317).

**Exit criteria:** `docker compose up` + one curl returns citations with section, vintage and page; hybrid+rerank beats dense-only on section hit rate; recall@10 ≥ 0.85; the comparison table is committed in `docs/eval/retrieval-w1.md`.

---

## Week 2 · Answers with a spine (30 Nov – 6 Dec)

- `[RAG]` Grounded prompt: numbered source block, "cite every claim as `[n]`", corpus-vintage and *applies-to* banner injected from the retrieved `doc_id`, token-budgeted context assembly.
- `[RAG]` **Refusal path:** refuse when top rerank score < τ, when no retrieved chunk shares a section with the query's lexical anchors, or when the question is dated outside the corpus. τ is set from the Week 1 score distribution, not guessed.
- `[RAG]` **Citation validator:** parse `[n]` → map to chunk → assert the section exists in the context → strip or reject unsupported claims; message carries `citation_valid` plus a reason.
- `[API]` `POST /api/v1/ask` SSE stream: `retrieval` → `token`×n → `citation`×n → `usage` → `done` | `error`; request id on every event; client disconnect cancels generation server-side.
- `[API]` `Generator` protocol with Ollama / OpenAI / Gemini adapters, per-adapter timeout, retry and price table (cost is computed, not claimed).
- `[UI]` Next.js 16 chat shell: streamed message, inline `[n]` markers, collapsible source list, explicit refusal state, scope banner, `⌘/Ctrl+Enter` submit, light/dark tokens.
- `[EVAL]` First end-to-end 40-question run; publish `docs/eval/baseline-w2.json`.
- `[INFRA]` CI: ruff + mypy + pytest + tsc + eslint + vitest on every PR.

**Exit criteria:** answer streams in the browser with clickable markers; citation accuracy ≥ 0.80, refusal correctness ≥ 0.90; uncited answers are impossible by construction, not by prompt hope.

---

## Week 3 · Product surface (7–13 Dec)

- `[UI]` **Citation viewer:** side panel with the exact section text, document, vintage, page; deep link `/s/[doc]/[section]?page=…`; "open in PDF" jumps to `#page=`.
- `[UI]` Conversation history on a server-issued session cookie (no login in v1), rename/delete, read-only share link; full empty/loading/error states; `aria-live` for streaming; keyboard-navigable; AA contrast.
- `[API]` Feedback endpoint (helpful / not + reason tags), aggregation endpoints `/api/v1/stats` and `/api/v1/evals/latest` so the eval numbers are visible in the product, not just in the repo.
- `[RAG]` History-aware follow-ups (query condensation before retrieval), embedding + retrieval caching, token-bucket rate limit at 20 req/min/IP.
- `[EVAL]` Prompt-variant comparison (3 variants, same golden set), failure taxonomy in `docs/eval/failures.md` — every miss classified as retrieval, grounding, or generation.
- `[DOCS]` "How it works" page with the disclaimer, tied to the architecture doc.

**Exit criteria:** search → answer → verified citation in ≤ 3 clicks; citation accuracy ≥ 0.85; a11y pass on the three primary flows; failure taxonomy has no unexplained misses.

---

## Week 4 · Harden and ship (14–20 Dec)

- `[INFRA]` Deploy: Next.js on Vercel, FastAPI (Docker) on Render, Postgres + pgvector on Neon; secrets in platform env; `/healthz`, `/readyz`, structured JSON logs, request-id propagation.
- `[INFRA]` Load test 20 concurrent SSE streams: record p95 first-token and end-to-end, cold-start behaviour, and cost per query; fix the tail (connection pooling, statement timeouts).
- `[EVAL]` Final 40-question report with per-question breakdown — **published including the failures**, plus the metric table in the README.
- `[TEST]` Playwright e2e (ask → cite → feedback → history), ≥ 70 % coverage on the retrieval and citation modules, security pass: prompt injection via retrieved text, XSS in rendered answers, no provider key in the browser bundle.
- `[DOCS]` README numbers filled in, 90-second demo recording, final architecture diagram, ADRs updated with the thresholds actually chosen.

**Exit criteria:** public URL works from a clean browser profile; CI green; README shows measured citation accuracy / latency / cost; demo recording exists.

---

## Metrics we commit to

| Metric | Target | Gate |
|---|---|---|
| Citation accuracy (40 Q) | ≥ 0.85 | PR blocked on > 3 pt regression |
| Fact recall | ≥ 0.80 | reported weekly |
| Refusal correctness | ≥ 0.90 | PR blocked on > 5 pt regression |
| Retrieval recall@10 | ≥ 0.85 | Week 1 exit |
| First token (local, 7B) | ≤ 1.5 s p95 | Week 4 load test |
| End-to-end p95 | ≤ 6 s local / ≤ 4 s hosted | Week 4 load test |
| Cost per query (hosted adapter) | ≤ ₹0.15 | computed in `usage` event |

Where a target is missed, the README says so and the failure taxonomy explains why. A number that cannot be reproduced does not go in the README.

---

## Non-goals (explicitly out of scope for v1)

Accounts and OAuth, document upload, multi-language, fine-tuning, mobile app, ITR filing, case-law/tribunal retrieval. Each is a credible v2 line; none of them is allowed to delay a deployed, measured v1.

---

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Act 2025 PDFs do not arrive this week | Headline accuracy risk: quoting a repealed Act | Week 1 starts with the 1961 corpus already in place; UI banner ships regardless; `applies_to_ay` metadata makes the gap visible rather than silent |
| Local 7B generation too slow on CPU | Demo feels broken | Streaming first (perceived latency), hosted adapter as fallback, model size chosen from a measured latency test, not vibes |
| Page numbers drift between PDF revisions | Citations point at the wrong page | Cite section as the primary key, page as a hint; record the doc hash in `documents` and re-verify page mapping on re-ingest |
| Table-of-contents or amended-section chunks sneak back in | Plausible but wrong citations | TOC heuristic already unit-tested; add a retrieval-quality check per document to the eval set |
| Scope creep into case law / ITR forms | Nothing ships | Non-goals list above; new ideas go to `docs/BACKLOG.md` |

---

## Repo map (target)

```
askdocs/
├── apps/
│   ├── web/          Next.js 16 — chat, citation viewer, corpus browser
│   └── api/          FastAPI — retrieval, generation, streaming, telemetry
├── packages/
│   └── shared/       generated API types + SSE event contract
├── scripts/          ingest.py (done), embed.py, load_db.py
├── eval/             golden_set.jsonl, retrieval_eval.py, e2e_eval.py, reports/
├── infra/            docker-compose.yml, Dockerfiles, migrations
├── data/             README.md, sources.json (raw/ and processed/ are gitignored)
└── docs/             PLAN.md, ARCHITECTURE.md, API.md, EVAL.md, DECISIONS.md
```

## Working agreement

- One commit per day-item, `type(scope): summary` — `data:`, `rag:`, `api:`, `ui:`, `eval:`, `infra:`, `docs:`. Docs for a day change in the same commit as the code.
- Every week ends with the metrics table updated and the exit criteria either met or explicitly waived in the README.
- No feature merges without a test or an eval case that would fail without it.

## Resume mapping

| Week | Line it earns on a résumé |
|---|---|
| 1 | Built a layout-aware, section-anchored ingestion pipeline over six government documents (11,080 chunks, 1,907 document/section pairs) — recovering 509 of 536 sections from a two-column gazette PDF — and a retrieval layer combining pgvector cosine search with Postgres full-text via Reciprocal Rank Fusion plus cross-encoder reranking. |
| 2 | Engineered grounded generation with server-side citation validation and a confidence-based refusal path, cutting unsupported claims by construction; streamed answers over SSE with per-request latency and cost telemetry. |
| 3 | Shipped the product surface — citation viewer with PDF page deep links, persistent history, feedback capture, and an in-app evaluation dashboard — with rate limiting and history-aware query rewriting. |
| 4 | Deployed a full-stack RAG service (Next.js + FastAPI + Neon pgvector) with CI regression gates on citation accuracy, load-tested to 20 concurrent streams, and documented measured accuracy, latency and cost per query. |
