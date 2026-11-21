# Corpus — what is in `data/`, and why you can trust the citations

Answers are built from official government documents, not scraped commentary. Every chunk maps to a **section number, a document, a vintage and a PDF page**, because in tax law the citation is the product.

## Documents (measured on this machine, not estimated)

| Document | Publisher | Vintage | Applies to | Pages | Sections | Chunks |
|---|---|---|---|---|---|---|
| **Income-tax Act, 2025** | Govt. of India — Act No. 30 of 2025 | as amended by **Finance Act, 2026** | Tax Year 2026-27 onwards | 687 | 509 of 536 + 16 schedules | 1,779 |
| **Income-tax Rules, 2026** | CBDT, Notification 22/2026 · G.S.R. 198(E) | notified 20 Mar 2026 | Tax Year 2026-27 onwards | 977 | 333 of 333 | 2,675 |
| Income-tax Act, 1961 | Govt. of India (consolidated, thc.nic.in) | up to Finance Act, **2021** | AY 2026-27 and earlier | 956 | 705 | 3,868 |
| CGST Act, 2017 | CBIC | as on 01.08.2021 | GST — ongoing | — | 175 | 578 |
| CGST Rules, 2017 | CBIC | as on 30.12.2017 | GST — ongoing | — | 169 | 863 |
| CBDT taxpayer FAQs | Income Tax Dept (HF mirror) | undated | eval / answer shape only | — | — | 1,317 |

**11,080 chunks · 8.72 M characters · 1,907 distinct (document, section) pairs.** Median chunk 891 chars, mean 787, hard cap 1,344.

Both Acts are in the corpus on purpose. The 2025 Act governs income from 1 April 2026; the 1961 Act still governs every tax year that began before it — returns, assessments, appeals, TDS corrections (s. 536 savings). An assistant that knows only one of them is wrong half the time, so `applies_to_ay` is stored per document and surfaced in every answer.

## Provenance

`incometaxindia.gov.in` returns **403 to this network** (WAF, including from a real browser). Both new documents were therefore retrieved from **Wayback Machine snapshots of the official pages**, and `data/sources.json` records the snapshot timestamp, byte count and SHA-256 prefix for each file:

| File | Retrieved via | Snapshot |
|---|---|---|
| `it_act_2025.pdf` | Wayback (`id_` raw PDF) | 2026-11-14 |
| `it_rules_2026.pdf` | Wayback, completed with a range resume after the first transfer truncated at 5 MB | 2026-04-12 |

A snapshot is not the live page: the Act text is the official consolidated text **as amended by Finance Act, 2026**, but a later amendment would not appear. Re-fetch before making freshness claims. PRS hosts the "as passed by Lok Sabha, 11.08.2025" copy — *not* used here, because it predates the Finance Act 2026 amendments.

## Rebuilding the corpus on another machine

`data/raw/` and `data/processed/` are gitignored: 20 MB of PDFs and a 9 MB chunk file are regenerable, and the FAQ mirror is not ours to redistribute. So a fresh clone has no corpus, and the bootstrap is three commands:

```bash
python scripts/fetch_corpus.py   # live URL first, Wayback snapshot as fallback, SHA-256 verified
python scripts/ingest.py         # rebuild chunks.jsonl (deterministic: two runs are byte-identical)
python scripts/doctor.py         # interpreter, poppler, per-document hashes, pinned chunk counts
```

`fetch_corpus.py` reads `data/manifest.json`, so it knows which route each document needs; it resumes truncated Wayback transfers with HTTP Range requests. One document cannot be automated: the **CBDT FAQ CSV** has no stable file URL — the manifest marks it `"acquire": "manual"` with a hint, and `doctor.py` treats its absence as a warning rather than a blocker, because it is eval-only and never shipped.

`doctor.py` prints the `corpus_hash` — quote it in every eval report. Numbers from different corpora are not comparable.

## Adding a document

1. Drop the PDF (or Q&A `.csv`) into `data/raw/`.
2. Add one entry to `data/manifest.json` — `doc_id`, `title`, `doc_type`, `vintage`, `applies_to_ay`, `source_url`, `sha256_16`, and the two layout facts below.
3. `python scripts/ingest.py`, then `python scripts/doctor.py`.

A PDF that is **not** in the manifest is still ingested — with inferred metadata and a loud warning — so a drop never silently does nothing. Auto-detection also picks the header style by counting distinct section numbers under each candidate; that is a starting point, not a substitute for the spot checks in the skill's verification checklist.

## Why the parser is layout-aware

The same statute, printed by two publishers, breaks naive parsers in two ways:

| Shape | Example | Extraction | Header style |
|---|---|---|---|
| Consolidated copy (thc.nic.in, CBIC) | `80C. Deduction in respect of life insurance premia...` | `pdftotext -layout` | `inline` |
| Gazette two-column PDF | `Repeal and savings.` then `536.(1) The Income-tax Act, 1961 ... is hereby repealed.` | `pdftotext -raw` | `above` |

With `-layout`, the gazette PDF's section numbers scatter across columns and 536 sections collapse to ~170. With `-raw`, the 1961 copy loses the indentation its sub-clauses rely on. So `pdf_mode` and `header_style` are **per-document facts in the manifest**, not global settings.

Header detection for the `above` style runs in two passes, because no single signal covers every section:

1. **Anchors** — a number line whose first sub-section marker `(1)` is on the same line or the next. High precision; blind to sections that have no sub-sections (13, 16, 25 …).
2. **Gap fill** — between two anchors, accept the line whose number equals the missing section and whose preceding line looks like a title. Bounding by the surrounding anchors is what stops a table row inside section 2 from claiming section 100.

Two traps that cost real chunks while building this, both now regression-checked against the four original documents (3,868 / 578 / 863 / 1,317 chunks must not move):

- The 2025 Act prints `9.(1)` with **no space** after the dot; requiring whitespace silently dropped 23 sections.
- Counting both header patterns in table-of-contents detection flagged rule-PDF body pages as TOC and dropped **28 chunks** of the CGST Rules.

Also: the Act's 16 schedules follow section 536, so they are emitted as their own sections (`SCHEDULE I` … `SCHEDULE XVI`). Without that, a deduction table cites "Section 536 — Repeal and savings".

**Honest gap:** 509 of 536 sections of the 2025 Act are anchored; sections whose headers match neither signal stay attached to the preceding section. The count is reported in `data/processed/stats.json` as `sections_unparsed`, and those sections are excluded from the golden set rather than guessed at.

## Chunk schema (`data/processed/chunks.jsonl`)

```json
{
  "id": "it-act-2025:536:0",
  "doc_id": "it-act-2025",
  "doc_title": "Income-tax Act, 2025",
  "doc_type": "act",
  "vintage": "Act No. 30 of 2025, as amended by Finance Act, 2026",
  "applies_to_ay": "Tax Year 2026-27 onwards",
  "section": "536",
  "section_title": "Repeal and savings",
  "chapter": "XXIII",
  "page": 584,
  "chunk_index": 0,
  "text": "536. (1) The Income-tax Act, 1961 (43 of 1961) is hereby repealed...",
  "chars": 612
}
```

## What is still missing

Deliberately not blocking v1, listed so nobody assumes otherwise:

1. **CBDT circulars 2015–2026** — explain contested readings; the highest-value addition after the Act. Blocked by the same WAF; needs a manual drop into `data/raw/circulars/`.
2. **ITR forms + instructions (Tax Year 2026-27)** — the FAQ corpus covers procedural shape, not the current-year forms.
3. **Tribunal / High Court judgments** — a different document shape (jurisdiction-bound, long); would need its own chunker and eval set.

## Licensing

- **Statutes and rules**: Government of India works. Reproduce with attribution; always show the source link and the "as on" date.
- **CBDT FAQs (HF mirror)**: the dataset declares **no license**. Used locally for evaluation and answer-shape reference only — never redistributed, never shipped inside the app.
- The product must say **"informational only, not legal advice"** in the UI.

## Evaluation

The golden set and metrics live in [`../docs/EVAL.md`](../docs/EVAL.md). Headline metric is **citation accuracy**: the cited section and document must match the expected ones, not just the prose.
