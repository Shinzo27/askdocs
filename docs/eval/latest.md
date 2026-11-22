## Retrieval run 2026-11-22 11:18 UTC

- questions: **25** (Week 1 subset)
- corpus_hash: `f7683ce4b68b` · extractor 26.11.0
- generation: none (retrieval only, zero LLM cost)

| Configuration | recall@10 | MRR@10 | section hit@1 | p50 ms | p95 ms |
|---|---|---|---|---|---|
| dense | 0.84 | 0.62 | 0.52 | 26 | 31 |
| lexical | 0.60 | 0.38 | 0.28 | 10 | 28 |
| hybrid | 0.80 | 0.59 | 0.52 | 31 | 48 |
| hybrid+rerank | 0.92 | 0.79 | 0.72 | 1188 | 2648 |

**Misses (hybrid+rerank):** q011, q018
