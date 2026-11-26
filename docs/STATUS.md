# Status — where AskDocs actually is

**Updated:** 2026-11-22, end of session. **Branch:** `main`, 16 commits ahead of `origin/main` after merging 3 upstream commits from a Linux box (poppler 24.02) that fixed the same parser bug — see the merge commit `9bf087a`.
**Corpus:** 11,069 chunks in `data/processed/`, 9,752 indexed (the eval-only CBDT FAQ is
deliberately excluded), `corpus_hash f7683ce4b68b`.

This file exists because the project got to a state that is easy to misread from the
README alone: Week 1 is solid, Week 2 works, and the accuracy number that matters is not
yet where it needs to be. Read this before the next session, then `docs/PLAN.md`.

---

## 1. What is verified

| Area | State | Evidence |
|---|---|---|
| Corpus rebuild from scratch | ✅ | `fetch_corpus.py` → `ingest.py` → `doctor.py` = **READY**; all 6 documents hash-verified |
| Retrieval (this machine) | ✅ | recall@10 **0.89** (gate 0.85), MRR 0.69 — `docs/eval/retrieval-w1.md` |
| API surface | ✅ | `/search`, `/sections/{doc}/{section}`, `/corpus/stats`, `/ask`, `/healthz`, `/readyz` |
| Streaming UI | ✅ *(browser-verified, echo generator)* | streams, chips with `aria-label`, chip opens section, Escape returns focus — `docs/screenshots/ask.png` |
| Deterministic core | ✅ | 28 unit tests: citation validator, refusal gate, context budget, sessions, RRF, dedupe, doc scoping |
| Lint / types | ✅ | ruff clean, `tsc --noEmit` clean |

## 2. What is built but failing its gate

End-to-end, 10 questions, qwen2.5:3b-instruct:

```
citation accuracy 0.80 (target 0.80) — reached 2026-11-23 by the RRF floor
fact recall 0.30 (target 0.80)   first token p95 30.8 s (target 1.5 s, measured
under CPU contention — see the latency note below)
refusal correctness 0.90 (target 0.90) must-not-say violations 0
first token p95 19.0 s (target 1.5 s)  end-to-end p95 31.9 s (target 6 s)
```

Model comparison, all measured here (`docs/eval/latest.md`, README):

| model | gen tok/s | prompt tok/s | first token p95 | citation acc | fact recall |
|---|---|---|---|---|---|
| 7B | 4.6 | 35 | ~70 s | not run to completion | — |
| 3B (isolated re-run, floor on, n=6) | 6.1 | 55 | 101.3 s ᶜ | **0.50** | 0.27 |
| 1.5B (floor on, n=6) | 9.4 | 49 | 12.1 s / 30.8 s ᶜ | **0.67** | 0.27 |

## 3. The three findings that shaped the work

1. **The corpus did not reproduce, and it was not the parser.** poppler 26.11.0 lifts the
   amendment footnote digit onto its own line, so headers read `[80C.` instead of
   `4[80C.` — 279 sections of the 1961 Act lost their anchor, including 80C/80CCD/80D/
   44ADA. Fixed; extractor version is now recorded and checked. (commit `6e48e10`)
2. **The CBDT FAQ in the index cost 0.11 recall.** FAQ text is question-shaped, so it
   out-ranked statute for every natural question while carrying no section to cite — and
   it is eval-only by licence. Excluding it took hybrid+rerank from 0.68 to 0.89. (`942d60b`)
3. **The reranker improves recall but *reduces* what reaches the model.** New
   `prompt_coverage` metric (does the correct section appear in the six sources the model
   actually sees):

   | config | recall@10 | prompt coverage |
   |---|---|---|
   | hybrid (RRF only) | 0.77 | **0.89** |
   | hybrid+rerank | 0.89 | **0.83** |

   Rerank lifts the candidate list from 0.77 to 0.89 and then drops the correct section
   out of the six that reach the model 6 % more often than plain RRF would have. Whether
   widening the prompt recovers that is **not yet measured** (see open questions).

## 4a. A contamination warning on today's latency numbers

The 2026-11-23 runs happened while another project's dev servers (SyncStream, turbopack)
were burning ~300% CPU and load average sat at 37. Every timing from that session — the
30.8 s first-token p95 included — is an upper bound measured on a machine that was not
idle. The 12.1 s figure from 2026-11-22 was taken with the box quiet. Re-measure on an
idle machine before quoting either, and say which state the machine was in.

## 4. Open questions — the ones I could not close today

Written down rather than guessed at; each one is a decision or an experiment for the
next session.

1. ~~**Why does rerank hurt prompt coverage?**~~ **Answered 2026-11-23 — it is the
   labelled input, and the fix is a trade, not a free win.** Measured by rerunning the
   full set with `RERANK_LABEL=0`:

   | rerank input | recall@10 | MRR@10 | hit@1 | prompt coverage |
   |---|---|---|---|---|
   | `Section — title — (document): text` | **0.89** | **0.69** | **0.60** | 0.83 |
   | raw passage text | 0.86 | 0.53 | 0.37 | **0.86** |

   So the prefix buys top-1 precision (hit@1 0.37 → 0.60, MRR 0.53 → 0.69) and pays
   3 points of prompt coverage. Keeping the labelled default: the metric the product
   leads with is *first* citation accuracy, which is driven by ranking, not by having
   the right section somewhere in the six. The residual idea — rerank with labels for
   order, then re-add any section that RRF ranked into its top six but rerank dropped —
   was tested the same day and **worked**: `RERANK_RRF_FLOOR=1 RERANK_FLOOR_SLOTS=3`
   re-admits what RRF ranked but rerank dropped, and moved citation accuracy from
   0.70 to 0.80 at n=10 (0.50 -> 0.67 at n=6) with over-refusals 1 -> 0 and refusal
   correctness 0.95 -> 1.00, while changing no ranking metric. It is the default now.
   Prompt coverage rises 0.83 -> 0.86, not to RRF's 0.89 — the floor is bounded at
   three extra sources, so two misses survive.

   **What it costs, measured:** 6 -> 9 sources per query and ~1,727 -> ~2,582 prompt
   tokens (+50%, on all four questions sampled). That is a direct hit on the metric
   already failing, which is the whole trade: the citation gate clears and first token
   gets slower. On a hosted model 2.6 k tokens is cheap; here it is not. If latency ever
   matters again, the cheap follow-up is to send floor-added sources truncated
   (title + first ~200 chars) rather than in full.
2. **Widening the pool is untested — do not claim otherwise.** `RERANK_TOP_K=6` measures
   0.83 prompt coverage across two runs (`16-55` four-config, `16-57` single-config, same
   corpus and same questions). The `k=8` and `k=10` runs were interrupted before writing a
   report, so there is **no result for either**. An earlier draft of this file said "8
   measures 0.83 too" — that was comparing two k=6 runs and it was wrong. If widening
   turns out not to help, the loss is ordering rather than truncation, which points at
   hypothesis 2; if it does help, the fix is a bigger prompt and more latency.
3. **Is the 3B better than the 1.5B?** No, and this was measured cleanly on 2026-11-23 after
   the port-collision bug was fixed: at identical settings and the same 6 questions the 3B
   scores 0.50 against 0.67, fails refusal correctness (0.83 vs 1.00), over-refuses twice,
   and all three of its citation misses are "cited nothing" rather than "cited wrongly". A
   model that goes quiet is not safer here; it fails the product's promise just as hard as a
   confident wrong answer, and the demo model stays 1.5B.

4. **Is the 0.50 citation ceiling retrieval or generation?** *Partly answered:* it was
   retrieval for the citation metric — feeding the model the sections RRF already found
   lifted citation to 0.80 without touching the prompt or the model. What remains is
   fact recall at 0.30, which the floor did not move at all, and that one is generation.
   Original framing: both 3B and 1.5B scored 0.50
   with identical failure shapes, so it looks like retrieval. But it is not proven that a
   perfect prompt would lift a 1.5B model to 0.80 — worth one run with the echo
   generator (which cites everything it is given) as an upper bound on what the prompt
   can support.
4. **§80CCE instead of §80C, §129 instead of §80E.** The model cites a *related* section
   rather than inventing one, which is a better failure than hallucination but still
   wrong. Unclear whether to treat this as a retrieval fix (do not retrieve aggregates for
   a provision query) or a prompt fix (cite the section the source header names).
5. **Model strategy is undecided.** Local tops out at 0.50 / 12 s on this 8 GB M2. A
   hosted adapter (OpenAI or Gemini) is written and **completely untested** — no key was
   available. That is the only path to the stated latency target.
6. **`AGENTS.md` is stale in two places** (line 6 still says 11,080 chunks; line 69 still
   shows `apps/ (Week 1+)`). The file is protected — my writes timed out awaiting
   approval — so it needs a manual edit or an explicit OK.

## 4a2. q001 is not retrieval, and the fix I tried did not work

Per-question misses from the floor A/B (n=6) are the useful detail, not the aggregate:

| arm | citation misses |
|---|---|
| floor off | q001 (cited 80CCE), q002 (cited nothing), q005 (cited 129) |
| floor on | q001 (cited 80CCE), q005 (cited 129) |

So the floor fixed exactly one thing: the question that cited *nothing*. It did not touch
q001, where §80C **was in the prompt at rank 2** and the model still picked §80CCE — the
ceiling section whose title literally contains "80C". That is citation selection at
generation time, not retrieval, and it is the single biggest remaining citation error.

**Tried and rejected (2026-11-23):** reordering sources so a section the question names by
number goes first (`promote_named_sections`, with unit tests). At n=6 it left citation
accuracy at 0.67 and changed q001 from "cited 80CCE" to "cited nothing", while over-refusals
went 0 -> 1 and refusal correctness 1.00 -> 0.92. The trade is wrong-citation -> refusal,
which is defensible in principle, but it wins no metric and costs the refusal gate that was
passing, so the code was removed rather than kept as a neutral change. It was reverted
before commit, so there is nothing in the history to find: the evidence is the e2e report
`eval/reports/2026-11-23T18-16-e2e.md` (`qwen2.5-1.5b-promote`) and this table. Do not
re-add it without a plan for the refusal regression.

## 4a3. Why the 3B numbers are still stale: my own harness collided with itself

The 3B re-run failed twice with different errors — `JSONDecodeError: Expecting value:
line 1 column 1` once and `httpx.ConnectError` once. Neither was the model and neither
was memory. All eval scripts started the API on **port 8000** and ended with
`pkill -f "uvicorn askdocs_api.main:app"`, and I ran two of them concurrently: the n=10
floor sweep killed the 3B job's server mid-question, and the 3B job killed the sweep's.

Rules for any future eval run, learned the hard way:
1. **One eval at a time.** These runs share a model process and a machine; concurrency
   corrupts timing even when it does not corrupt the numbers.
2. **Unique port per run** (`--base-url` is already parameterised; use 8123+).
3. **Kill by PID, not by pattern.** `pkill -f uvicorn` reaches into every other session's
   server, including ones you cannot see.
4. **Never read the gate's exit code through a pipe.** `python eval/e2e_eval.py | tail -16`
   reports `tail`'s status, so a run that printed `GATE FAILED` looks like `EXIT=0`. Both
   harnesses do `return 1` on failure (verified by pointing one at a dead port: exit 1), so
   the gate is real — the shell was lying. Redirect to a file and check `$?`, or use
   `PIPESTATUS`.

Every timing in this file from the 2026-11-23 session also carries the CPU-contention
caveat above, so treat the numbers as directionally right and the timings as upper bounds.

## 4b. The floor's own failure mode, seen in real output

`/search "80C tuition fees"` with the floor on returns nine sources, and three of them are
junk: `it-act-1961 §5`, `§3`, `§8`, `§4` — and, worse, `cgst-rules-2017 §15` and `§14`, GST
procedural rules in an income-tax answer. That is the floor doing exactly what it was told:
re-admit what RRF ranked, and RRF's tail is noise (recall@10 0.77 against rerank's 0.89).

So the floor buys citation accuracy by injecting distractors, and cgst-rules-2017 in a 1961-Act
prompt is the kind of source a wrong-but-confident answer is built from. It has not shown up as
a must-not-say violation yet (0 in both arms), but it is one bad model away from being one.

The fix to try next, in order:
1. **Doc consistency:** only re-admit a floor section from the same `doc_id` as the reranked
   top-1, or one that `infer_doc_scope` allows. Cheapest, and it alone would have excluded both
   GST sections above.
2. **RRF score floor:** require the addition's RRF score ≥ 0.6 × the best RRF score, so the tail
   needs to be reasonably ranked to earn a slot.
3. Both, then re-run the n=10 citation comparison — anything that touches the floor must
   re-measure 0.80, because it currently passes and a refinement can quietly lose that.

## 5. How to resume

```bash
cd /Volumes/Work/projects/askdocs
export PATH=/opt/homebrew/bin:$PATH        # git, pdftotext, ollama live here

make doctor                 # corpus integrity; must print READY
make up                     # Postgres + pgvector  (Docker Desktop must be running)
make api                    # FastAPI on :8000 (reads .env)
make web                    # Next.js on :3000
ollama serve &              # only if you want real generation

make test                   # 28 unit tests
make eval-retrieval         # 25-question retrieval subset
make eval-e2e               # full path against the running API
```

Model choice is configuration, not code:

```bash
GENERATOR_PROVIDER=ollama OLLAMA_MODEL=qwen2.5:3b-instruct make api
GENERATOR_PROVIDER=echo   make api      # no model: exercises SSE + validation only
GENERATOR_PROVIDER=openai OPENAI_API_KEY=... make api
```

## 6. What was left running when I stopped

Everything is stopped except Docker Desktop and the Postgres container:

| Service | State |
|---|---|
| Postgres (`askdocs-db`) | **running**, 9,752 chunks loaded |
| FastAPI `:8000` | stopped |
| Next.js `:3000` | stopped |
| Ollama (`:11434`) | stopped; 7B + 3B + 1.5B pulled (7.6 GB on disk) |

## 7. The next three things I would do

1. **Close open question 1** with one experiment: rerank on raw passage text vs the
   labelled prefix, measuring `prompt_coverage`. It is a 20-minute run and it decides
   whether the prefix stays.
2. **Then** per-section neighbour expansion (include the adjacent chunk of a selected
   section when the budget allows) — the sub-clause problem behind q001/q002.
3. **Then** Week 3's surfaces (corpus browser wired to `/corpus/stats`, history, eval
   dashboard), which do not depend on the model question at all.

---

## 8. Machine #2 (Windows 11, 2026-11-23) — the handoff test, and what it broke

A second machine cloned the repo and ran the documented bootstrap. It did **not** reproduce
out of the box. Four real portability bugs, all now fixed in code rather than in prose:

| Problem | Symptom | Fix |
|---|---|---|
| Git for Windows ships **pdftotext 4.00** (2017) ahead of any modern poppler on PATH | corpus rebuilt as 11,093 chunks / 1,987 pairs, matching no pin set; `doctor` FAIL | `PDFTOTEXT` env override in `ingest.py` + `doctor.py`; pin set added for the modern build |
| Ancient extractor silently wins | "chunk counts match the pins (9763 chunks)" style ambiguity → doctor now names the build it matched | doctor prints the pin label and warns when `stats.json`'s extractor differs from PATH |
| `Makefile` assumed a POSIX venv (`PY := .venv/bin/python`) and `python3` | every target failed on Windows before running anything | `VENV_BIN` auto-detects `Scripts/` vs `bin/`; `PYTHON ?= python3 || python` |
| `make test` needed a `.env` (config fails fast on missing `DATABASE_URL`) | 5 failures that say nothing about the code | `apps/api/tests/conftest.py` sets a dummy URL with `setdefault` |
| `make typecheck` needed `node_modules`, which is gitignored | "This is not the tsc command you are looking for" | node_modules is a real make target; `typecheck` and `web` depend on it |

**Result on machine #2 after the fixes:** modern poppler **26.09.0** reproduces the corpus
**exactly** (11,069 chunks / 1,968 pairs — same as the macOS 26.11.0 pin, now recorded as its
own pin set), `doctor` READY, `make test` **48 passing** (28 pytest + 20 unittest),
`make lint` clean, `make typecheck` clean (5 genuine mypy errors found and fixed:
`list` without parameters, `Any` from a numpy index, `None`-able section key, untyped
factory, unannotated dict).

Not yet run on machine #2: `make db` + `load` + `eval-retrieval`/`eval-e2e` (needs Docker
Desktop up and the bge-small model download), i.e. the retrieval *numbers* are still only
measured on the macOS box. Everything up to the corpus is now reproduced twice.

### Pending: `AGENTS.md` is stale and protected

`AGENTS.md` needs three edits that a write-approval timeout blocked. Apply them by hand or
approve an agent edit:

1. Line 6 → `**State:** Week 1 done (recall@10 0.89); Week 2 built, accuracy gate open (fact recall 0.27 vs 0.80). Corpus 11,069 chunks (9,752 indexed; eval-only FAQ excluded). Read docs/STATUS.md, then docs/PLAN.md.`
2. Line 27 → `python scripts/ingest.py        # 11,069 chunks (count depends on poppler build)`
3. Line 38 table → add `| macOS arm64 (2026-11-22) | 26.11.0 | 9,752 | 11,069 |` and `| Windows 11 (2026-11-23) | 26.09.0 | 9,752 | 11,069 |`, and change the Windows row's `11,080` to the FAQ-included column name that matches reality.

Also worth adding to `AGENTS.md` (traps section): *git-bash ships pdftotext 4.00 and wins
over a modern install — set `PDFTOTEXT` rather than editing PATH.*
