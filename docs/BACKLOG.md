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
| ONNX / quantised cross-encoder | Week 1 shipped fp32 on CPU: 1.8 s p50 for 30 candidates, ~7× the 250 ms budget. Accuracy is the reason to keep the stage | Rerank is still the p95 bottleneck after the Week 4 load test |
| Fine-tuned answer model | A 7B with a strong prompt plus validation is the honest baseline; tuning before measuring is guessing | Grounding failures dominate the failure taxonomy after prompt fixes |

## Known gaps (documented, not hidden)

- Both Acts and the 2026 Rules are in the corpus; 513 of 536 sections of the 2025 Act are anchored, and the 23 unanchored ones are reported as `sections_unparsed` rather than guessed at.
- CBDT circulars are missing — "why" questions can only be answered from statute text and FAQs.
- The Income-tax Act, 1961 copy is consolidated to Finance Act 2021, so post-2021 amendments are not reflected. This is the largest accuracy risk in the project and the reason vintages are stored per document.
- Page numbers are only as stable as the PDF revision and the extractor; sections are the primary citation key and pages are the hint.
- Chunk counts are extractor-dependent (pdftotext 26.11.0 is the pinned build). A different poppler version shifts counts by a handful without changing the text, so eval numbers are compared only within one `corpus_hash`.
