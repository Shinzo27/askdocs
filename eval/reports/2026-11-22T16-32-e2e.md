## End-to-end run 2026-11-22 16:32 UTC

- provider/model: **ollama/qwen2.5:3b-instruct** · prompt 31926134
- corpus_hash: `f7683ce4b68b`
- questions: 10 (10 with an expected section)

| Metric | Value | Target | Status |
|---|---|---|---|
| Citation accuracy | 0.50 | ≥ 0.80 | ❌ |
| Fact recall | 0.40 | ≥ 0.80 | ❌ |
| Must-not-say violations | 0 | 0 | ✅ |
| Refusal correctness | 0.90 | ≥ 0.90 | ✅ |
| Over-refusals (in-corpus) | 2 | 0 | ❌ |
| First token p95 | 18986 ms | ≤ 1500 ms | ❌ |
| End-to-end p95 | 31918 ms | ≤ 6000 ms | ❌ |
| Cost per query | ₹0.0 | ≤ ₹0.15 | ✅ |

**Citation misses:** q001 (got none), q002 (got none), q005 (got 129), q008 (got none), q009 (got 21)
