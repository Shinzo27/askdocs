## Retrieval run 2026-11-22 16:46 UTC

- questions: **35** (full set)
- corpus_hash: `f7683ce4b68b` · extractor 26.11.0
- generation: none (retrieval only, zero LLM cost)

| Configuration | recall@10 | MRR@10 | section hit@1 | p50 ms | p95 ms |
|---|---|---|---|---|---|
| dense | 0.80 | 0.61 | 0.51 | 29 | 46 |
| lexical | 0.54 | 0.33 | 0.23 | 11 | 42 |
| hybrid | 0.77 | 0.58 | 0.51 | 30 | 51 |
| hybrid+rerank | 0.89 | 0.69 | 0.60 | 1591 | 3111 |

**Misses (hybrid+rerank):** q011, q015, q018, q030
