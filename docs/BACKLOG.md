# Backlog

Parked deliberately so they do not delay a measured v1. Each entry names the signal that would justify building it.

## v2 candidates

| Idea | Why it is not in v1 | Signal that would trigger it |
|---|---|---|
| Accounts + Google sign-in | Session cookies already carry history; auth adds a provider, an email flow and a retention policy | Users asking to keep history across devices |
| Upload your own document | The value is the curated, versioned corpus — arbitrary uploads would make citation accuracy unmeasurable | A repeated request from a CA firm |
| Tribunal / case-law retrieval | Different corpus shape (judgments are long and jurisdiction-bound); needs its own chunker and eval set | Citation accuracy stable on statute QA for 2+ weeks |
| Section-level diff between Act 1961 and Act 2025 | Genuinely useful, but it is a second product surface | Act 2025 corpus ingested and answers from it look correct |
| Multi-language (Hindi, Gujarati) | Retrieval quality in English is not yet proven; translation would hide retrieval errors | English citation accuracy ≥ 0.85 sustained |
| ITR form recommender | Deterministic logic, not retrieval — a different feature entirely | A user interview where "which ITR" dominates |
| Streaming rerank (progressive citations) | Complexity for a 250 ms stage | First-token latency becomes the top complaint |
| Fine-tuned answer model | A 7B with a strong prompt plus validation is the honest baseline; tuning before measuring is guessing | Grounding failures dominate the failure taxonomy after prompt fixes |

## Known gaps (documented, not hidden)

- Income-tax Act, 2025 and Rules, 2026 are not in the corpus until the Week 1 drop. Until then every answer carries the `AY ≤ 2026-27` banner.
- CBDT circulars are missing — "why" questions can only be answered from statute text and FAQs.
- The Income-tax Act, 1961 copy is consolidated to Finance Act 2021, so post-2021 amendments are not reflected. This is the largest accuracy risk in the project and the reason vintages are stored per document.
- Page numbers are only as stable as the PDF revision; sections are the primary citation key and pages are the hint.
