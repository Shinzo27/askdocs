# AskDocs — corpus notes

Answers over Indian tax law with **citations you can check**, built from official
government documents, not scraped blog posts.

## What is in `data/raw` right now

Everything here was fetched from this machine and its size/http status measured.

| doc | publisher | vintage | size | chunks |
|---|---|---|---|---|
| Income-tax Act, 1961 | Govt. of India (via `thc.nic.in`) | consolidated to **FA 2021** | 8.8 MB · 956 pp | 3,868 |
| CGST Act, 2017 | CBIC | as on 01.08.2021 | 1.8 MB | 578 |
| CGST Rules, 2017 | CBIC | as on 30.12.2017 | 4.0 MB | 863 |
| CBDT taxpayer FAQs | Income Tax Dept (HF mirror) | undated | 760 KB · 1,116 Q&A | 1,317 |

**6,626 chunks · 4.9M characters**, median chunk 817 chars, mean 746, hard cap 1,344.

Note the 1961 Act is **not dead weight**: it still governs every tax year that
began before 1 April 2026 (returns, assessments, appeals), so a useful assistant
must retrieve from both Acts and say which one applies.

## The gap you must close

`incometaxindia.gov.in` **blocks this network** — WAF returns 403 even to a real
browser. That means the **Income-tax Act, 2025** (which replaced the 1961 Act on
1 April 2026) is not in the corpus, and CBDT circulars are missing.

Shipping a tax assistant that quotes a repealed Act is the fastest way to look
careless. Before this goes public, drop these into `data/raw/` from an Indian
residential connection:

1. **Income-tax Act, 2025** — https://incometaxindia.gov.in/income-tax-act-202511
2. **Income-tax Rules, 2026** — https://incometaxindia.gov.in/income-tax-rule-2026
3. **CBDT circulars 2023–2026** — https://www.incometaxindia.gov.in/circulars
   (save as `circulars/YYYY-circular-NN.pdf`)

Then `python scripts/ingest.py` picks them up with no code change.

## Why section-aware chunking

Naive fixed-window chunking returned the **table of contents** for "80C" — the
heading list, not the deduction rules. Two filters now prevent that:

- TOC pages are dropped (short-line density heuristic, see `is_toc_page`);
- sections are split on `N.`/`12A.` headers, tolerating the `4[80C.` footnote
  prefix that Indian statute PDFs use for amended provisions.

Result: every chunk carries `section`, `section_title`, `chapter` and `page`, so
an answer can render as *"Section 80C, Chapter VI-A, p. 330"* and a reader can
verify it in the PDF.

## Chunk schema (`data/processed/chunks.jsonl`)

```json
{
  "id": "it-act-1961:80C:0",
  "doc_id": "it-act-1961",
  "doc_title": "Income-tax Act, 1961",
  "doc_type": "act",
  "section": "80C",
  "section_title": "Deduction in respect of life insurance premia...",
  "chapter": "VI-A",
  "page": 330,
  "chunk_index": 0,
  "text": "...",
  "chars": 758
}
```

## Licensing

- **Statutes and rules**: Government of India works. Reproduce with attribution;
  always show the source link and the "as on" date.
- **CBDT FAQs (HF mirror)**: the dataset declares **no license**. Use it locally
  for evaluation and answer-shape reference only — do not redistribute it, and
  do not ship it inside the app.
- The product must say **"informational only, not legal advice"** in the UI.

## Evaluation plan (the part most RAG demos skip)

Hand-write a golden set of 40 questions from the corpus, each with:

- `question`
- `expected_section` (e.g. `80C`) — the citation must match, not just the prose
- `answer_facts` — 2–4 atomic facts the answer must contain
- `must_not_say` — the tempting wrong answer (e.g. quoting a withdrawn limit)

Metrics: **citation accuracy**, **fact recall**, **refusal correctness** (questions
outside the corpus must be refused, not answered), plus p95 latency and
cost-per-query. A wrong answer with a confident citation is worse than a refusal,
so citation accuracy is the headline metric, not RAGAS's aggregate score.
