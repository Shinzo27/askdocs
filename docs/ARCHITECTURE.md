# Architecture

Two deployables and one database. Everything else is a library.

> The `apps/` layout is the Week 1 target. Today the repository contains `scripts/ingest.py` and the corpus metadata — the corpus pipeline is the only part that exists, and it is the part everything else depends on.

```
apps/web   Next.js 16 · App Router · TypeScript strict   →  Vercel
apps/api   FastAPI · Python 3.12                          →  Render (Docker)
           Postgres 16 + pgvector + tsvector              →  Neon
           Ollama (local default) / OpenAI / Gemini       →  external or sidecar
```

```mermaid
flowchart TB
  subgraph Browser
    C[Chat surface<br/>streamed tokens, [n] markers]
    V[Citation viewer<br/>section · vintage · page]
    H[History / feedback]
  end

  subgraph API[FastAPI]
    Q[Question intake<br/>validate · rate limit · request id]
    RW[Query condensation<br/>for follow-ups]
    RET[Retriever<br/>hybrid + RRF]
    RR[Reranker<br/>cross-encoder]
    CA[Context assembly<br/>token budget · numbered sources]
    GEN[Generator adapter<br/>ollama | openai | gemini]
    CV[Citation validator<br/>marker → chunk → section]
    GR[Grounding guard<br/>refuse when unsupported]
    TEL[Telemetry<br/>latency · tokens · cost]
  end

  DB[(chunks + vectors<br/>+ tsvector)]
  LOG[(query_log<br/>messages · citations)]

  C --> Q --> RW --> RET
  RET --> DB
  RET --> RR --> CA --> GR --> GEN
  GEN --> CV --> C
  CV --> V
  CV --> H
  CV --> LOG
  TEL --> LOG
```

## Request lifecycle

1. **Intake.** `POST /api/v1/ask` validates the question (length, language, control characters), attaches a request id, applies the rate limit, and opens the SSE stream immediately so the UI can show retrieval progress.
2. **Condensation.** For a follow-up turn, the previous two exchanges are condensed into one standalone question (cheap local model, 150-token cap). A failed condensation falls back to the raw question rather than blocking the request.
3. **Hybrid retrieval.** The condensed question is embedded with `bge-small-en-v1.5` (384-d, in-process) and sent to two queries in parallel:
   - dense: `ORDER BY embedding <=> $1 LIMIT 50`, filtered by `doc_type` when the user pins a document;
   - lexical: `ts_rank_cd(tsv, websearch_to_tsquery('english', $1)) LIMIT 50`.
   Candidates are fused with **Reciprocal Rank Fusion** (`k = 60`), which is rank-based and therefore does not require calibrating cosine against `ts_rank` — the two scores are not comparable and pretending otherwise is a common bug.
4. **Rerank.** The fused top-30 passages go through `cross-encoder/ms-marco-MiniLM-L-6-v2`; the top-6 survive after section-level dedupe (two chunks from Section 80C should not eat the whole prompt).
5. **Assembly.** Sources are numbered in rerank order, with header `[n] doc_title — Section X, Chapter Y, p. N (as on <vintage>)`. The token budget is enforced from the back: the least relevant source is dropped first, never the head of the question.
6. **Grounding guard.** If the top rerank score is below τ, or the retrieved set contains no section that matches the question's statutory anchors, the request short-circuits to a refusal template naming what *is* in the corpus. Refusal is cheaper, faster and more honest than a fluent miss.
7. **Generation.** The adapter streams tokens. The prompt forbids outside knowledge, requires `[n]` on every substantive claim, and forbids inventing section numbers.
8. **Citation validation.** Emitted `[n]` markers are resolved to chunks; a marker pointing outside the supplied context fails validation. The message is stored with `citation_valid` and, when the strict mode is on, unsupported sentences are stripped before they reach the client.
9. **Telemetry.** One `query_log` row per request: retrieval scores, rerank scores, latency split (retrieve / rerank / first token / total), token counts, computed cost, provider, model, citation validity, refusal flag. This table is what the eval dashboard and the README numbers read from.

## Data model

```sql
CREATE TABLE documents (
  doc_id        text PRIMARY KEY,
  title         text NOT NULL,
  doc_type      text NOT NULL,           -- act | rules | faq | circular
  publisher     text,
  vintage       text,                    -- "consolidated to FA 2021"
  applies_to_ay text,                    -- "AY <= 2026-27"
  source_url    text,
  sha256        text NOT NULL,           -- detects silent PDF revisions
  pages         int
);

CREATE TABLE chunks (
  id            text PRIMARY KEY,        -- "it-act-1961:80C:0"
  doc_id        text REFERENCES documents(doc_id),
  section       text,
  section_title text,
  chapter       text,
  page          int,
  chunk_index   int,
  text          text NOT NULL,
  chars         int NOT NULL,
  embedding     vector(384),             -- bge-small-en-v1.5
  tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
);
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_tsv_idx       ON chunks USING gin (tsv);
CREATE INDEX chunks_section_idx   ON chunks (doc_id, section);

CREATE TABLE messages (
  id             uuid PRIMARY KEY,
  conversation_id uuid NOT NULL,
  role           text NOT NULL,          -- user | assistant
  content        text NOT NULL,
  model          text,
  provider       text,
  citation_valid boolean,
  refused        boolean DEFAULT false,
  latency_ms     int,
  cost_inr       numeric(10,4),
  created_at     timestamptz DEFAULT now()
);

CREATE TABLE citations (
  message_id  uuid REFERENCES messages(id) ON DELETE CASCADE,
  marker      int NOT NULL,              -- the [n] the user sees
  chunk_id    text NOT NULL,
  doc_id      text NOT NULL,
  section     text,
  page        int,
  rerank_score real,
  PRIMARY KEY (message_id, marker)
);

CREATE TABLE feedback (
  message_id  uuid REFERENCES messages(id) ON DELETE CASCADE,
  verdict     text NOT NULL,             -- helpful | wrong_citation | wrong_fact | refused_wrongly
  note        text,
  created_at  timestamptz DEFAULT now()
);
```

`citations` is a real table, not a JSON blob: the feedback loop needs to answer "which section gets flagged most often", and that question is a `GROUP BY`, not a parsing exercise.

## Grounding contract

| Rule | Enforcement |
|---|---|
| Answer only from supplied context | System prompt + grounding guard; provider temperature 0.1 |
| Every substantive claim carries `[n]` | Citation validator rejects unknown markers |
| Never invent a section number | Marker must resolve to a chunk whose `section` exists |
| Say which Act and vintage apply | Source header injected into the prompt; surfaced in the UI banner |
| Refuse when unsure | Score threshold τ + anchor check, tuned from the Week 1 score distribution |
| No outside knowledge, no advice | Prompt constraints; the UI carries the "informational only" disclaimer |

τ is a configuration value, changed only with an eval run attached to the PR that changes it.

## Failure modes

| Failure | Detection | Response |
|---|---|---|
| Provider timeout / 5xx | adapter timeout (30 s) + retry once | SSE `error` event with retry hint, `query_log` row marks provider failure |
| Client disconnects mid-stream | `request.is_disconnected()` | generation task cancelled; tokens already billed are still logged |
| Empty retrieval | zero candidates after fusion | refusal template, no LLM call at all (saves cost, avoids hallucination) |
| Reranker unavailable | model load failure | degrade to RRF order, log `degraded: rerank`, the eval suite would catch a persistent drop |
| Oversized context | token budget exceeded during assembly | drop tail sources until it fits; never truncate mid-sentence from the head |
| Prompt injection in statute text | pattern scan on retrieved chunks + instruction hierarchy in the prompt | flagged in `query_log`, answer still citation-bound |

## Performance budget

| Stage | Budget (local, 7B) |
|---|---|
| Embed + hybrid retrieval | ≤ 120 ms |
| Rerank 30 → 6 | ≤ 250 ms |
| First token | ≤ 1.5 s |
| Full answer (450 tokens) | ≤ 6 s p95 |
| DB round-trips per question | ≤ 3 |

Instrumentation is per-stage in `query_log`; the p95 in the README is computed from that table, not from a stopwatch.

## Deployment

- **Web** → Vercel; only `NEXT_PUBLIC_API_URL` is exposed, no provider keys reach the browser bundle.
- **API** → Render Docker service; `/healthz` (process alive), `/readyz` (DB + embedding model + provider reachable).
- **DB** → Neon Postgres with pgvector; migrations run as a release step, never on import.
- **Local** → `docker compose up` runs api, web, Postgres and Ollama; the corpus loader seeds from `data/processed/chunks.jsonl`.

Environment contract lives in `.env.example`; a missing variable fails fast at boot with the variable name, not with a stack trace three layers deep.
