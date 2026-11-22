# Week 1 retrieval — measured, with the failures named

Run: **2026-11-22**, 35 scorable questions (the 25-question Week 1 subset plus the
10 remainder), corpus `f7683ce4b68b`, pdftotext 26.11.0, `BAAI/bge-small-en-v1.5`
(384-d) + `cross-encoder/ms-marco-MiniLM-L-6-v2`. No LLM call: retrieval only, so a
run costs nothing and can be repeated after any index change.

| Configuration | recall@10 | MRR@10 | section hit@1 | p50 ms | p95 ms |
|---|---|---|---|---|---|
| dense only (cosine top-50) | 0.80 | 0.61 | 0.51 | 22 | 25 |
| lexical only (IDF-weighted FTS) | 0.54 | 0.33 | 0.23 | 16 | 52 |
| hybrid (RRF, k=60) | 0.77 | 0.58 | 0.51 | 31 | 60 |
| **hybrid + cross-encoder rerank** | **0.89** | **0.69** | **0.60** | 1829 | 2558 |

Gate: recall@10 ≥ 0.85 → **passed** by the reranked configuration. The table is
reproduced by `make eval-retrieval`; `eval/reports/<timestamp>.json` holds every
question with its first-correct rank.

## What the numbers changed

Each row below is a fix that came from a measurement, not a hunch. The before/after
is what makes them worth writing down.

| Measurement | Before | After | What actually caused it |
|---|---|---|---|
| lexical recall@10 | 0.08 | 0.54 | `websearch_to_tsquery` ANDs every term, so a sentence-length question matched almost nothing. Replaced with an OR over the query's lexemes. |
| lexical recall@10 | 0.16 | 0.54 | `ts_rank_cd` has no notion of rarity: "deduct" appears in 1,653 chunks, "80C" in 12, so the common stem ranked first. Replaced with `Σ 1/(1+ndoc)` from a materialised `lexeme_stats` table. |
| hybrid+rerank recall@10 | 0.68 | 0.89 | The CBDT FAQ mirror was in the retrieval index. FAQ text is question-shaped, so it out-ranked statute for every natural question while carrying no section to cite — and it is documented as eval-only, never shipped. Now excluded at load. |
| hybrid+rerank hit@1 | 0.36 | 0.60 | The cross-encoder saw raw chunk text, which often never repeats its own section number. It now sees `Section · title — (document): text`. |

An earlier attempt that did **not** survive measurement: truncating the query to its
rarest N lexemes scored 0.32 at best. Rarity is not informativeness — "regardless"
is rarer than "registration" — so the IDF weighting replaced it.

## Failures, classified

Four of 35 questions miss on the reranked configuration. Each was inspected, not
guessed: the mechanism below is what the retrieved top-5 actually showed.

| Question | Asked | Expected | What ranked instead | Mechanism |
|---|---|---|---|---|
| q011 | When is profit on sale of a capital asset charged as capital gains? | `it-act-1961 §45` | `1961 §54`, `2025 §77`, `1961 §50B` | **retrieval, vocabulary** — §45's body says "profits or gains arising from the transfer of a capital asset"; the question says "charged as capital gains", which is the *title* language of neighbouring exemptions. §45 never entered the fused candidate pool. |
| q015 | Is interest on a fixed deposit taxable, and under which head? | `it-act-1961 §56` | `it-act-2025 §56` | **retrieval, version trap** — right section number, wrong Act. The 2025 Act's §56 outranked the 1961 Act's, which `docs/EVAL.md` counts as a failure even when the number matches. |
| q018 | Who must compulsorily register under GST regardless of turnover? | `cgst-act-2017 §24` | `cgst-act-2017 §22`, then `cgst-rules-2017 §24` ×3 | **retrieval, document + wording** — "compulsorily register" matches §22's threshold language; the Rules' rule 24 then outranks the Act's section 24. |
| q030 | What can an assessee do if they disagree with an order? | `it-act-1961 §246A` | `2025 §275`, `1961 §144C`, `rules §90` | **retrieval, vocabulary** — the question contains no statutory term ("appeal", "Commissioner (Appeals)"); "disagree with an order" is not in the statute's language. |

Three of the four are the same root cause: **the right section number inside the
wrong document**. Both Acts and both rule sets are in one index, and a question that
does not name its Act leaves the retriever to pick a vintage. That is a Week 3
query-rewriting and document-scoping problem, not a reason to tune the retriever
further — and it is exactly the failure the mixed-vintage banner exists to make
visible to the reader.

Fixed during Week 1 by the changes above: q001 (omitted §80F outranked §80C), q012,
q013 (§54/§54F reached rank 13–21; labelled rerank input pulled them in), q021, q028,
q033.

No question failed for **grounding** or **generation**: there is no generator in Week 1,
by design. That column starts at Week 2.

## Known weaknesses before Week 2

- **Rerank latency**: ~1.8 s p50 for 30 candidates on CPU, against a 250 ms budget.
  The accuracy is real, so the fix is throughput (ONNX/quantised encoder, batching,
  or a cache), not removing the stage. A 20-candidate pool was measured: recall@10
  0.86, p50 957 ms — the documented fallback if latency has to win, at a 3-point
  accuracy cost. Tracked in `docs/BACKLOG.md`.
- **Only 35 of 40 questions are scorable here**: the 5 refusal traps have no
  expected section, and refusal correctness needs a generator, so they score from
  Week 2.
- **q011/q015/q018/q030 are vocabulary gaps**, not index bugs: they are the honest
  argument for query rewriting (Week 3) rather than another retriever tweak.
