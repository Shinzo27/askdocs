# Evaluation reports

Populated from Week 1 onward by `make eval`. Nothing here is hand-edited — the runner writes the JSON and the markdown table in the same run, and the README reads the most recent full report.

Naming: `YYYY-MM-DDTHH-MM.json` (machine) and `YYYY-MM-DDTHH-MM.md` (table pasted into the repo docs).

| Report | Run | Citation accuracy | Notes |
|---|---|---|---|
| [`retrieval-w1.md`](retrieval-w1.md) | 2026-11-22 | n/a (retrieval only) | recall@10 0.89 hybrid+rerank vs 0.80 dense-only on 35 questions; 4 misses classified in [`failures.md`](failures.md) |
| `latest.md` (e2e) | 2026-11-22 | 0.50 | 10 questions, qwen2.5:3b-instruct: fact recall 0.40, refusal correctness 0.90, first token p95 19 s. Gate missed — see the README's Week 2 section |

Two rules for this directory:

1. A report is never edited after it is written. Regrading means a new report with a new timestamp.
2. Every report states its `corpus_hash`, prompt version, provider and model. Numbers from different corpora are not compared.
