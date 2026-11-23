## End-to-end run 2026-11-23 18:26 UTC

- provider/model: **ollama/qwen2.5-3b-floor-on-isolated** · prompt 31926134
- corpus_hash: `f7683ce4b68b`
- questions: 6 (6 with an expected section)

| Metric | Value | Target | Status |
|---|---|---|---|
| Citation accuracy | 0.50 | ≥ 0.80 | ❌ |
| Fact recall | 0.27 | ≥ 0.80 | ❌ |
| Must-not-say violations | 0 | 0 | ✅ |
| Refusal correctness | 0.83 | ≥ 0.90 | ❌ |
| Over-refusals (in-corpus) | 2 | 0 | ❌ |
| First token p95 | 101341 ms | ≤ 1500 ms | ❌ |
| End-to-end p95 | 137418 ms | ≤ 6000 ms | ❌ |
| Cost per query | ₹0.0 | ≤ ₹0.15 | ✅ |

**Citation misses:** q001 (got none), q005 (got none), q006 (got none)
