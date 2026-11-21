# API Contract — v1

Base URL: `https://api.askdocs.app/api/v1` (local: `http://localhost:8000/api/v1`).
All responses are JSON unless the endpoint is an SSE stream. Timestamps are ISO-8601 UTC.

Conventions follow the project's `api-design` rules: plural kebab-case resources, no verbs in URLs (except action endpoints such as `feedback`), semantic status codes, and one error envelope shape.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/ask` | Ask a question; streams the answer over SSE |
| `GET` | `/search` | Retrieval only — passages, scores, sections (no LLM call) |
| `POST` | `/conversations` | Create a conversation |
| `GET` | `/conversations` | List conversations for the current session (cursor paginated) |
| `GET` | `/conversations/{id}` | Conversation with messages and citations |
| `PATCH` | `/conversations/{id}` | Rename |
| `DELETE` | `/conversations/{id}` | Delete (cascades messages and citations) |
| `POST` | `/messages/{id}/feedback` | Record a verdict on an answer |
| `GET` | `/sections/{doc_id}/{section}` | Full section text + page + vintage (powers the citation viewer) |
| `GET` | `/corpus/stats` | Documents, chunks, sections, vintage — the corpus table in the UI |
| `GET` | `/evals/latest` | Latest evaluation report (the dashboard reads this) |
| `GET` | `/stats` | p50/p95 latency, refusal rate, citation-valid rate, cost per query |
| `GET` | `/healthz` · `/readyz` | Liveness · readiness (DB, model, provider) |

## `POST /ask`

```json
{
  "question": "How much can I deduct under 80C for my child's tuition fees?",
  "conversation_id": "9f2c...",
  "doc_scope": ["it-act-1961", "it-act-2025"],
  "stream": true
}
```

`doc_scope` is optional; when omitted, all documents are searched and the answer surfaces the vintage of whichever document it used.

Validation: `question` 3–500 characters, UTF-8, control characters stripped; `conversation_id` must belong to the caller's session cookie, otherwise `403`.

### Response — `text/event-stream`

Each event is `event: <type>` + `data: <json>`. Events arrive in this order:

```
event: retrieval
data: {"request_id":"r-8f21","candidates":50,"fused":30,"reranked":6,"top_score":0.83,"sections":["80C","10(14)"]}

event: token
data: {"text":"Section 80C allows a deduction of up to "}

event: token
data: {"text":"₹1,50,000 [1] for tuition fees paid "}

event: citation
data: {"marker":1,"doc_id":"it-act-1961","section":"80C","section_title":"Deduction in respect of life insurance premia...","chapter":"VI-A","page":330,"vintage":"consolidated to FA 2021","rerank_score":0.83}

event: usage
data: {"prompt_tokens":2140,"completion_tokens":318,"provider":"ollama","model":"qwen2.5:7b-instruct","cost_inr":0.0,"latency_ms":{"retrieve":96,"rerank":212,"first_token":1180,"total":5240}}

event: done
data: {"message_id":"m-3c9a","citation_valid":true,"refused":false}
```

Refusal follows the same envelope, with the answer produced by the template and no `citation` events:

```
event: token
data: {"text":"The question is outside the documents I can verify ..."}

event: done
data: {"message_id":"m-3c9b","citation_valid":true,"refused":true,"reason":"no_section_match"}
```

`reason` is one of `low_score`, `no_section_match`, `out_of_corpus_date`, `empty_retrieval`.

Errors mid-stream are delivered as a final `error` event (the HTTP status is already `200` by then):

```
event: error
data: {"code":"provider_timeout","message":"Generation timed out after 30s","request_id":"r-8f21","retryable":true}
```

### Example

```bash
curl -N -X POST http://localhost:8000/api/v1/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the GST registration threshold for a services business?","stream":true}'
```

## `GET /search`

```bash
curl "http://localhost:8000/api/v1/search?q=presumptive%20taxation%20freelancer&limit=6&debug=1"
```

```json
{
  "data": [
    {
      "chunk_id": "it-act-1961:44ADA:1",
      "doc_id": "it-act-1961",
      "doc_title": "Income-tax Act, 1961",
      "vintage": "consolidated to FA 2021",
      "section": "44ADA",
      "section_title": "Special provision for computing profits ... profession",
      "chapter": null,
      "page": 118,
      "text": "...",
      "scores": { "dense": 0.71, "lexical": 0.42, "rrf": 0.031, "rerank": 0.88 }
    }
  ],
  "meta": { "returned": 6, "candidates": 100, "took_ms": 143 }
}
```

`debug=1` requires no auth locally and is disabled in production; it exists so the eval harness and the failure taxonomy read exactly what the model saw.

## Feedback

```json
POST /api/v1/messages/m-3c9a/feedback
{ "verdict": "wrong_citation", "note": "quoted the 2021 limit, not the current one" }
```

`verdict ∈ {helpful, wrong_citation, wrong_fact, refused_wrongly, other}`. One verdict per message per session; re-submitting replaces it.

## Errors

```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "20 requests per minute per IP. Retry in 30 seconds.",
    "request_id": "r-8f22",
    "details": [{ "field": "question", "message": "Exceeds 500 characters" }]
  }
}
```

| Status | `code` | When |
|---|---|---|
| 400 | `invalid_json` | Malformed body |
| 403 | `forbidden` | Conversation not owned by this session |
| 404 | `not_found` | Unknown conversation, message or section |
| 409 | `conflict` | Feedback already set for another session's message |
| 413 | `payload_too_large` | Question over 500 chars after normalisation |
| 422 | `validation_error` | Schema violation, field-level `details` |
| 429 | `rate_limit_exceeded` | 20 req/min/IP, `Retry-After` header set |
| 503 | `provider_unavailable` | All generation adapters down; `retryable: true` |

Internal details (stack traces, SQL, provider payloads) never appear in a response body; they appear in the structured log under the same `request_id`.

## Sessions and limits

- Anonymous session: signed httpOnly cookie, 30-day expiry, created on first `/ask`. No login in v1.
- Rate limits: `20/min` per IP for `/ask`, `60/min` for `/search`, `3/min` for `/feedback` bursts.
- Request body cap 8 KB; answer cap 700 tokens; context cap 6 sources.
- Streaming: server cancels generation when the client disconnects (checked between chunks), and logs partial usage.

## Versioning

`/api/v1` from day one. Additive changes (new event type, new field) ship inside v1; removing or renaming fields, changing an event shape, or changing the meaning of `refused` requires `/api/v2`. SSE events carry a `type` so clients can ignore unknown ones without breaking.

The TypeScript client contract in `packages/shared` is generated from the FastAPI OpenAPI schema, so an API change that forgets the frontend fails typecheck instead of failing in the browser.
