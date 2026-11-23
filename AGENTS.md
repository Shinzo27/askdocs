# AGENTS.md — start here

Any agent (Claude Code, Codex, Cursor, OpenCode, Hermes, a human in a text editor) should be able to pick this repo up on a clean machine and continue without asking questions. This file is the contract; the docs it links are the detail.

**Project:** AskDocs — grounded question-answering over Indian tax law where every answer carries a citation (document + section + page + vintage) a reader can verify.
**State:** corpus built and verified (11,080 chunks, 6 documents). Retrieval, generation and UI are Week 1–4 work; see `docs/PLAN.md`.
**Repo:** https://github.com/Shinzo27/askdocs · MIT (code only)

## Read order

1. `AGENTS.md` (this file) — invariants and commands.
2. `docs/PLAN.md` — what week we are in and what "done" means for it.
3. `docs/ARCHITECTURE.md` — request lifecycle, data model, grounding contract.
4. `docs/STANDARDS.md` — the two external skill sets that define code and UI quality (**ECC** `github.com/affaan-m/ECC` for code review, API design, security, testing; **UI UX Pro Max** `github.com/nextlevelbuilder/ui-ux-pro-max-skill` for design, accessibility and responsive layout). **Required before writing code or UI.** The committed design contract is `design-system/askdocs/MASTER.md`.
5. `docs/API.md`, `docs/EVAL.md`, `docs/DECISIONS.md` when touching those areas.
6. `data/README.md` — how the corpus was built and what is honestly missing.

## Bootstrap on a clean machine

```bash
# any OS; pdftotext is the only external binary
git clone https://github.com/Shinzo27/askdocs.git
cd askdocs
python -m venv .venv            # Debian/Ubuntu without python3-venv: add --without-pip
. .venv/bin/activate            # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python scripts/fetch_corpus.py  # re-downloads the 6 documents, hash-verified
python scripts/ingest.py        # 11,080 chunks -> data/processed/ (count depends on poppler build)
python scripts/doctor.py        # must print READY before you trust anything
python -m unittest discover -s tests   # parser traps + the pin gate (stdlib only)
```

`data/raw/` and `data/processed/` are gitignored on purpose: 28 MB of government PDFs plus a 12 MB chunk file are regenerable, and the FAQ mirror is not ours to redistribute. Never commit them, never "fix" a failing check by editing a recorded hash.

**Handoff tested on two machines.** Clone → `fetch_corpus.py` → `ingest.py` → `doctor.py` = READY with two warnings (the CBDT FAQ CSV needs a manual download). Chunk counts depend on the poppler build, so `stats.json` records `pdftotext_version` and `doctor.py` checks the pin set for that build:

| Machine | pdftotext | Without FAQ | With FAQ |
|---|---|---|---|
| author's Windows (2026-11-21) | not recorded | 9,763 | 11,080 |
| Ubuntu 24.04 (2026-11-23) | 24.02.0 | 9,774 | 11,091 |

A build with no pin set fails `doctor.py`. Spot-check its output (section counts per document in `stats.json` against `data/README.md`, plus a grep for headers the parser rejected), then **add** a set to `PIN_SETS`. Eval reports quote `corpus_hash` **and** the poppler version.

## Invariants — do not break these

| Invariant | Why | Enforced by |
|---|---|---|
| Per-document chunk counts stay at the values pinned for the poppler build (`PIN_SETS`) | Two parser "improvements" silently dropped 28 chunks and 23 sections; one poppler build silently dropped 279 | `scripts/doctor.py`, `tests/test_doctor.py` |
| A citation is `(doc_id, section)`, with page as a hint | Pages drift between printings; sections are the legal address | chunk schema |
| Every chunk carries `vintage` + `applies_to_ay` | The 1961 Act still governs tax years before 1 Apr 2026; the 2025 Act governs after | `data/manifest.json` |
| Refuse rather than guess | A wrong answer with a confident citation is the worst product behaviour in tax | `docs/EVAL.md` metrics |
| The CBDT FAQ corpus is never shipped or committed | The mirror declares no licence | `data/README.md` |
| Eval numbers quote `corpus_hash` | Numbers from different corpora are not comparable | `doctor.py` prints it |

## Verification gates

A change is not done because it runs. It is done when the matching gate passes:

| Touching | Gate | Command / artefact |
|---|---|---|
| Parser, manifest, corpus | chunk pins + spot checks + parser tests | `python scripts/doctor.py`, `python -m unittest discover -s tests` |
| Retrieval / prompts / τ | eval thresholds, no >3 pt regression | `make eval` (Week 1), `docs/eval/*.json` |
| API surface | contract + typed client compile | `docs/API.md`, `packages/shared` typecheck |
| UI | design-system checklist, a11y, responsive | `design-system/askdocs/MASTER.md` pre-delivery list |
| Any code | ECC review skills | `docs/STANDARDS.md` gate table |

## Where things live

```
AGENTS.md                 this file — agent entry point
scripts/ingest.py         PDF/CSV -> section-tagged chunks (manifest-driven, layout-aware)
scripts/fetch_corpus.py   re-acquire the corpus, hash-verified, Wayback fallback
scripts/doctor.py         environment + corpus integrity check
data/manifest.json        one entry per document: ids, vintage, pdf_mode, header_style, hash
data/sources.json         provenance: URL, route, snapshot timestamp, bytes, pages
design-system/askdocs/    persisted design system (MASTER.md + tokens.json + pages/)
docs/                     PLAN, ARCHITECTURE, API, EVAL, DECISIONS, STANDARDS, BACKLOG
apps/ (Week 1+)           web/ Next.js 16 · api/ FastAPI
```

## Working agreement

- One commit per day-item: `type(scope): summary` with `data:`, `rag:`, `api:`, `ui:`, `eval:`, `infra:`, `docs:`. Docs for a day change in the same commit as the code.
- New document → one `data/manifest.json` entry, then `fetch_corpus.py` + `ingest.py` + `doctor.py`. No parser edits unless a spot check proves the format differs.
- New UI surface → read `design-system/askdocs/MASTER.md` first; put deviations in `design-system/askdocs/pages/<page>.md`, never by editing Master casually.
- Anything not measurable is a preference, not a fact: do not put unverified numbers in the README.

## Known traps (already paid for, do not rediscover)

1. `pdftotext -layout` destroys two-column gazette PDFs; `-raw` destroys the 1961 copy's indentation. `pdf_mode` is per document.
2. The 2025 Act prints `9.(1)` with **no space** after the dot — a regex requiring whitespace silently drops sections.
3. Counting two header patterns in TOC detection drops body pages (−28 chunks on CGST Rules).
4. Schedules follow the last section; without `SCHEDULE I…XVI` keys, deduction tables cite "s. 536 — Repeal and savings".
5. The PRS "as passed 11.08.2025" bill is a cross-check, **not** a corpus source — it predates Finance Act 2026 and collides on section numbers.
6. `incometaxindia.gov.in` 403s from some networks; Wayback `id_` snapshots of the same URLs deliver the bytes (and truncate — resume with Range).
7. poppler 24.02 `-layout` moves the footnote superscript of `4[80C.` onto its own line, leaving `[80C.`. Requiring the digit dropped 279 sections of the 1961 Act on Linux, so the prefix is `\d{0,2}\[`. Same PDFs, different poppler build, different chunks: that is why the pins are per build.
