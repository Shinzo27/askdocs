# Evaluation

The evaluation harness exists because "it looks good in the demo" is not a measurement. Every claim in the README must be reproducible with `make eval`.

## Golden set

40 hand-written questions, each derived from a specific section of the corpus. Stored as JSONL in `eval/golden_set.jsonl`.

```json
{
  "id": "q017",
  "question": "How much can I deduct under section 80C for my child's tuition fees?",
  "expected_sections": ["80C"],
  "expected_doc": "it-act-1961",
  "answer_facts": [
    "tuition fees qualify under 80C",
    "the overall 80C ceiling is 1,50,000"
  ],
  "must_not_say": ["1,00,000", "no limit"],
  "category": "deduction",
  "difficulty": "easy",
  "notes": "The pre-2014 ceiling of 1,00,000 is the classic stale answer."
}
```

Fields:

- `expected_sections` — the citation must resolve to one of these. Section match is **strict**: `80C` is not `80CCD`, and a document mismatch (`it-act-1961` when `it-act-2025` applies) is a failure even with the right section number.
- `answer_facts` — 2–4 atomic, checkable facts. Not prose, not vibes.
- `must_not_say` — the tempting wrong answer. This is what catches a model that retrieved the right section but quoted a withdrawn limit.
- `category` / `difficulty` — for slicing the report.

### Distribution

| Category | Count | What it tests |
|---|---|---|
| Deductions & exemptions (80C, 80D, 80CCD, HRA, LTA) | 10 | Dense retrieval on numeric thresholds |
| Capital gains & house property | 6 | Long sections, multi-chunk answers |
| GST registration, thresholds, ITC | 8 | Cross-statute retrieval and correct document attribution |
| Procedural / documentation (FAQ-derived) | 6 | Answer shape and completeness |
| Refusal traps (outside the corpus) | 5 | Refusal correctness — state tax, tribunal rulings, hypotheticals |
| Version traps (repealed or amended provisions) | 5 | `must_not_say` penalties; Act 1961 vs Act 2025 — both are now in the corpus, so the answer has to pick the right one rather than the only one |

Ten questions (`holdout`) are never used while tuning prompts or τ. They are scored every full run and reported separately, so an improvement that only exists on the tuned set is visible as a holdout regression.

Questions may only target sections the parser actually anchored. The Income-tax Act, 2025 has 513 of 536 anchored (23 reported as `sections_unparsed` in `data/processed/stats.json`); a question whose section is not anchored is removed from the set rather than graded against text attached to the previous section. The golden set also pins `corpus_hash`, so adding a document invalidates the run instead of silently shifting the baseline.

## Metrics

| Metric | Definition | Target |
|---|---|---|
| **Citation accuracy** | share of answers whose first `[1]` citation matches `expected_sections` **and** `expected_doc` | ≥ 0.85 |
| **Fact recall** | mean over questions of `matched_facts / len(answer_facts)` | ≥ 0.80 |
| **Must-not-say violation rate** | share of answers containing any `must_not_say` string | 0 (any violation is reported per question) |
| **Refusal correctness** | mean of *out-of-corpus refusal rate* and *(1 − over-refusal rate on in-corpus questions)* | ≥ 0.90 |
| **Retrieval recall@10** | share of questions where a chunk from `expected_sections` appears in the top-10 candidates (pre-generation) | ≥ 0.85 |
| **MRR@10** | mean reciprocal rank of the first correct-section chunk | reported |
| **First-token latency** | p50 / p95 over the run | p95 ≤ 1.5 s |
| **End-to-end latency** | p50 / p95 over the run | p95 ≤ 6 s |
| **Cost per query** | tokens × provider price + embedding amortisation | ≤ ₹0.15 hosted |

Answers are graded by a rubric prompt with a versioned judge model, and a **20 % human-audited sample** is recorded in `eval/reports/human_audit.md`. Judge disagreement above 10 % invalidates the run and the rubric prompt is fixed before any number is published.

## Running it

```bash
make eval                 # full 40-question run, local generator
make eval PROVIDER=openai # same set against a hosted adapter
make eval-retrieval       # retrieval-only: recall@10, MRR, no LLM cost
make eval-compare BASE=eval/reports/2026-12-02T10-14.json
```

Outputs:

- `eval/reports/<timestamp>.json` — machine-readable, every question with scores, retrieved sections, final answer, latency split.
- `eval/reports/<timestamp>.md` — the human table, pasted into `docs/eval/latest.md`.
- Exit code `1` if any gate is missed, so CI can use it directly.

## CI gate

| Stage | Scope | Gate |
|---|---|---|
| PR (every push) | 15-question smoke subset | citation accuracy may not drop > 3 pt vs `main`; must-not-say violations must be 0 |
| PR touching prompts/τ/reranker | 15-question subset + retrieval metrics | retrieval recall@10 may not drop > 3 pt |
| Nightly / pre-release | full 40 + holdout split | all targets above; report published |

The baseline is the JSON from the last green `main` run, so the gate is relative to reality rather than to a number someone typed once.

## Anti-gaming rules

1. **Prompts are versioned files** (`apps/api/prompts/*.txt`) — a prompt change is a reviewable diff, and the CI eval stage runs on it.
2. **No question-specific branching.** Retrieval config, τ and prompt text must be identical for every question in a run; a `if question == ...` path in production code fails review.
3. **Holdout split is untouched** during tuning. Reported separately, always.
4. **Fixed generation settings** for scoring runs: temperature 0.1, seed fixed where supported, max 700 tokens.
5. **Corpus version pinned** in the report (`corpus_hash` from the embedding manifest). Numbers from different corpora are never compared.
6. **Failures are published.** The final report includes every miss with its category, and `docs/eval/failures.md` explains the mechanism (retrieval, grounding, or generation) behind each one.

## What "refusal correctness" actually costs

Over-refusing is the easy way to make citation accuracy look good. The metric pair (`out-of-corpus refusal rate` with `over-refusal rate`) makes both errors visible, and the in-corpus target is stated explicitly: **at most 1 in 10 valid questions may be refused** for the run to count as passing.

## Reporting format

```markdown
## Run 2026-12-18 · corpus v2 · ollama/qwen2.5:7b · prompt v3

| Metric | Value | Target | Status |
|---|---|---|---|
| Citation accuracy | 0.87 | ≥ 0.85 | ✅ |
| Fact recall | 0.81 | ≥ 0.80 | ✅ |
| Must-not-say violations | 2 | 0 | ❌ |
| Refusal correctness | 0.92 | ≥ 0.90 | ✅ |
| Retrieval recall@10 | 0.90 | ≥ 0.85 | ✅ |
| First token p95 | 1.32 s | ≤ 1.5 s | ✅ |
| End-to-end p95 | 5.4 s | ≤ 6 s | ✅ |

Failures: q004 (retrieval), q019 (generation), q031 (version trap — quoted the 1961 limit).
```

A run with a ❌ is still published. The README's headline number is the most recent full run, with its timestamp.
