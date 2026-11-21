# Decisions

Short ADRs. Each records the option that was rejected, because that is the part future readers cannot reconstruct.

---

## ADR-001 — Section-aware chunking instead of fixed windows

**Decision.** Split statute PDFs on `N.` / `12A.` section headers and keep `section`, `section_title`, `chapter`, `page` on every chunk.

**Why.** Fixed 1000-character windows returned the *table of contents* for the query "80C" — a heading list, not the deduction rules — and lost the ability to cite anything better than "somewhere in the PDF". Section splitting makes the citation the unit of retrieval, which makes evaluation possible at all.

**Cost.** Two filters had to be written and tested: TOC-page detection, and tolerance for the `4[80C.` footnote prefix Indian statute PDFs use for amended provisions. Without the second, hundreds of amended sections silently vanish.

---

## ADR-002 — Postgres + pgvector instead of a dedicated vector database

**Decision.** One Postgres instance holds vectors, full-text index and product data.

**Why.** The workload is 6.6 k chunks — three orders of magnitude below where HNSW tuning becomes a problem. A second datastore would add a deployment, a backup policy and a consistency bug (chunk deleted from one store, alive in the other) in exchange for latency nobody would notice.

**Rejected.** Qdrant/Weaviate/Pinecone: operationally heavier, and none of them solves the actual hard part (hybrid fusion + rerank).

---

## ADR-003 — Hybrid retrieval with Reciprocal Rank Fusion

**Decision.** Dense top-50 ∥ lexical top-50, fused with RRF (`k = 60`), then reranked.

**Why.** Each retriever has a failure the other covers: vector search misses exact statutory phrases ("notwithstanding anything contained in"), full-text misses paraphrase ("deduction for my kid's school fees"). RRF is rank-based, so it needs no calibration between cosine distance and `ts_rank_cd` — normalising those two into one score is a bug waiting to happen.

**Cost.** Two queries and a rerank per request instead of one. Measured at ~140 ms total on the dev box; acceptable against a 1.5 s first-token budget.

---

## ADR-004 — Local embeddings, provider-agnostic generation

**Decision.** `bge-small-en-v1.5` runs in-process; the generator sits behind one `Generator` protocol with Ollama as the default and OpenAI/Gemini adapters available.

**Why.** Embeddings must be deterministic and free — the eval numbers are only comparable if the same text produces the same vector, and re-encoding the corpus on every key change would be a silent regression source. Generation is the part worth swapping, so it is the part behind an interface.

**Rejected.** Hosted embeddings by default: costs money per re-index, and ties the reproducibility of the evaluation to a vendor key.

---

## ADR-005 — Refusal as a first-class outcome

**Decision.** A low rerank score or a missing section anchor short-circuits to a refusal template before the LLM is called.

**Why.** A wrong answer with a confident citation is the worst possible product behaviour in tax, and it scores identically to a good answer on every "did it respond" metric. Refusing early is also cheaper: no generation tokens, ~200 ms response.

**Cost.** Refusal correctness had to be split into two metrics (out-of-corpus refusal, over-refusal) so that refusing everything cannot look like an improvement.

---

## ADR-006 — Citation validation server-side, not prompt-side

**Decision.** `[n]` markers are resolved to retrieved chunks after generation; unknown or out-of-context markers fail the message.

**Why.** A prompt instruction is a hope. Validation is a check. With `citation_valid` stored per message, the metric stops being a claim about the prompt and becomes a queryable fact.

---

## ADR-007 — SSE instead of WebSockets

**Decision.** `text/event-stream` for token streaming.

**Why.** One-directional server→client flow, works through every proxy, reconnects with `Last-Event-ID` semantics, and needs no connection registry on the server. WebSockets would buy bidirectionality the product does not use.

---

## ADR-008 — Anonymous sessions, no accounts in v1

**Decision.** Signed httpOnly cookie stores a session id; conversations belong to that session.

**Why.** Login adds a provider dependency, an email flow and a data-retention policy to a project whose difficulty is retrieval quality. The history feature (and the feedback loop) work without it. Accounts are a v2 line, listed in `docs/BACKLOG.md`.

---

## ADR-009 — Publish failures, not just headline accuracy

**Decision.** The eval report ships with per-question failures and a mechanism classification; a ❌ row stays in the published table.

**Why.** An accuracy number with no visible failures is unfalsifiable. The failure taxonomy is also the most useful engineering artefact in the repo: it tells the next reader where the pipeline actually breaks.

---

## ADR-010 — Corpus vintages are data, not code

**Decision.** `documents.vintage` and `documents.applies_to_ay` are columns; the UI banner and the prompt header read them.

**Why.** The Income-tax Act, 1961 applies to AY ≤ 2026-27 and the Act, 2025 applies after — a distinction that will keep changing. Encoding it in a prompt string would make every future amendment a code change; encoding it in the database makes it a data update with an audit trail.

---

## ADR-011 — Parsing is layout-aware and anchor-based, declared per document

**Decision.** `data/manifest.json` declares, per document, `pdf_mode` (`layout` | `raw`) and `header_style` (`inline` | `above`). Unknown PDFs are auto-detected by counting distinct section numbers under each style. The `above` style is parsed in two passes: `(1)`-anchored headers first, then gap-fill bounded by neighbouring anchors.

**Why.** The same statute printed by two publishers breaks a parser in opposite ways. `pdftotext -layout` on the gazette PDF of the 2025 Act scatters section numbers across two columns and collapses 536 sections to ~170; `-raw` on the 1961 copy loses the indentation its sub-clauses depend on. Neither mode is right globally, so it is a per-document fact.

**Rejected.** One clever regex for both shapes. It looked fine on the 1961 Act and silently dropped 23 sections of the 2025 Act that print `9.(1)` with no space after the dot.

**Cost, measured.** Three real bugs surfaced while building this, each of which silently lost content:

- counting both header patterns in TOC detection dropped **28 chunks** of the CGST Rules (body pages misread as an arrangement);
- a front-matter bound on TOC detection re-admitted the 1961 Act's trailing index (+76 chunks of junk);
- schedules defaulting to the preceding section made every deduction table cite "Section 536 — Repeal and savings", fixed by emitting `SCHEDULE I`…`XVI` as their own sections.

The four original documents now have an asserted chunk count (3,852 / 579 / 889 / 1,317), so any of these regressions fails a test instead of quietly shrinking the corpus.

**Fourth bug, found on a different machine (2026-11-22).** The same PDFs, the same parser, a newer poppler — and 80C disappeared. poppler 26.11.0 lifts the amendment footnote digit onto its own line, so the header reads `[80C.` where the pattern expected `4[80C.`; 279 sections of the 1961 Act lost their anchor and were absorbed by the section above them. Two lessons, both now encoded: the extractor is part of the corpus provenance (`stats.json` records the version, `doctor.py` compares it to the pin and warns instead of silently failing a sound corpus), and "the parser is unchanged" is not the same claim as "the output is unchanged". Recovery raised the 1961 count from 705 to 768 section keys — the pins moved *up*.

**Honest residual.** 23 of 536 sections in the 2025 Act match neither header signal; they stay attached to the preceding section, are reported as `sections_unparsed`, and are excluded from the golden set. Fixing them means font-level extraction (bold spans), which is a Week 2 problem at the earliest — a section count that is 95 % right and honestly reported beats a parser that lies.

---

## ADR-012 — Two external skill sets are the review gate, and their output is committed

**Decision.** Code quality is judged against **ECC** (`github.com/affaan-m/ECC`) and UI quality against **UI UX Pro Max** (`github.com/nextlevelbuilder/ui-ux-pro-max-skill`). Their artefacts live in the repo: the gate table in `docs/STANDARDS.md` and the design system in `design-system/askdocs/`.

**Why.** "Looks good" is not reviewable and does not survive a change of machine or agent. Committing the design system (Master + tokens + page overrides) means the next agent produces the same UI decisions instead of a new opinion; naming the ECC skills per layer means a review finding is traceable to a rule rather than to taste.

**Consequences.** Regenerating the design system is a reviewed change (`--force` is not allowed silently, because the curated version deliberately overrides the generator's landing-page pattern). A change that passes the code gate but fails the design checklist is not done, and vice versa.

**Rejected.** Vendoring ECC itself into the repo: it is an agent-harness surface with hooks and commands that do not transfer to every harness (its installer writes nothing into a Hermes profile), so pointing at the source of truth plus recording the decisions is more durable than copying it.

---

