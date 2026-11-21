# Standards — how "done" is decided

Two external skill sets decide whether this repo's code and UI are acceptable. They are not inspiration; they are the review criteria, and the artefacts they produce live in this repo so a different agent on a different machine reaches the same answer.

| Toolchain | Scope | Artefact in repo |
|---|---|---|
| **ECC** — [github.com/affaan-m/ECC](https://github.com/affaan-m/ECC) (MIT) | code review, architecture, API design, security, testing, delivery | gate table below + PR notes |
| **UI UX Pro Max** — [github.com/nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) (MIT) | design system, accessibility, interaction, responsive layout | `design-system/askdocs/MASTER.md`, `tokens.json`, `pages/` |

---

## 1. ECC — engineering review

ECC is an agent-harness operating system: 72 subagents (`agents/`), 328 skills (`skills/`), 99 slash-command shims (`commands/`), plus `rules/` and `hooks/`. The root of that repo is the source of truth; the platform adapters only map it (`.claude-plugin/`, `.codex/`, `.cursor/`, `.opencode/`).

### Install (pick one per harness — do not stack)

```bash
# Claude Code: native plugin
/plugin marketplace add affaan-m/ECC
/plugin install ecc@ecc

# Any harness with the script surface: resolve a plan, dry-run, then apply
node scripts/install-plan.js --list-profiles
node scripts/install-plan.js --profile minimal --target codex --json
node scripts/install-apply.js --profile minimal --target codex --dry-run

# readiness check
npm run harness:audit -- --format text
```

**Hermes caveat, verified against ECC's own guide:** ECC's installer targets Claude Code, Codex and Kimi config surfaces and writes **nothing** into a Hermes profile. Inside Hermes, install individual `skills/<name>/SKILL.md` files from the repo — and only the `SKILL.md` reaches the model: ECC's hooks, `commands/` shims and `agents/` prompts have no Hermes equivalent. Curate, do not bulk-install.

### Which parts this project uses

| Layer | ECC skill / agent | Applied when |
|---|---|---|
| Corpus + parser | `coding-standards` | any edit to `scripts/*.py` — naming, immutability, comments that explain *why* |
| Retrieval + DB | `postgres-patterns`, `backend-patterns` | pgvector/HNSW indexes, `EXPLAIN` before claiming a query is fast, repository/service layering |
| HTTP surface | `api-design` | endpoint shape, status codes, error envelope, SSE contract, versioning — `docs/API.md` is the output |
| Grounding + abuse cases | `security-review` | prompt injection via retrieved statute text, XSS in rendered answers, provider keys in the browser bundle |
| Web UI | `frontend-patterns`, `react-patterns` | streaming state, server/client boundaries, hooks discipline |
| Tests | `test-driven-development`, `e2e-testing`, `react-testing` | failing test first for behaviour; Playwright for ask → cite → feedback → history |
| Delivery | `docker-patterns`, `git-workflow`, `requesting-code-review` | compose stack, branch/commit shape, pre-merge review |
| Whole change | `code-reviewer` subagent (ECC) or `requesting-code-review` skill (Hermes) | before every merge |

Rules of engagement: **no feature merges without a test or an eval case that would fail without it**, and a review finding is fixed or explicitly waived in the PR — not silently dropped.

---

## 2. UI UX Pro Max — the UI contract

Searchable design intelligence: 80 styles (51 active), 194 product palettes, 74 font pairings, 130 UX guidelines, 105 icons, 25 chart types, 22 stacks. MIT.

### Install

```bash
npm install -g ui-ux-pro-max-cli
uipro init --ai claude      # or: cursor | windsurf | codex | antigravity …
```

In Hermes the skill is already loaded (`ui-ux-pro-max`); its search script is invoked by absolute path, which differs per machine — never hardcode it in repo docs:

```bash
python "<skills-dir>/ui-ux-pro-max/scripts/search.py" "<query>" --domain style
```

### Design system for this repo

Generated once, then **curated by hand** — regeneration is a reviewed change, never a silent overwrite (`--force` requires explicit approval, because a new generation discards product decisions):

```bash
python "<skills-dir>/ui-ux-pro-max/scripts/search.py" \
  "legal tax document research assistant citations chat trustworthy minimal serif" \
  --design-system --persist --tokens dtcg -p "AskDocs" --output-dir "."
# -> design-system/askdocs/MASTER.md + tokens.json
```

Retrieval protocol when building any surface:

1. Read `design-system/askdocs/MASTER.md`.
2. If `design-system/askdocs/pages/<page>.md` exists, **its rules override Master**; create a page file for deviations instead of editing Master.
3. Otherwise Master only.

The generated palette (scholarly navy `#1E3A5F`, citation gold `#B45309`, EB Garamond headings, Lato body) was kept; the generic landing-page pattern it proposed was rejected — this product is a research workspace, not a newsletter. Product-specific surfaces, component rules and the pre-delivery checklist live in `MASTER.md`.

### The non-negotiables it imports

1. Accessibility first: 4.5:1 text contrast, visible focus, 44×44 px targets, `aria-live` for streamed answers, no meaning by colour alone.
2. SVG icons only (Lucide/Heroicons) — never emoji as icons.
3. `cursor-pointer` and 150–300 ms transitions on everything clickable; respect `prefers-reduced-motion`.
4. Responsive at 375 / 768 / 1024 / 1440; no horizontal scroll, no zoom disabling.
5. Essential text reflows without clipping at 200 % zoom and with large text settings.

---

## 3. Verification matrix

| Claim in the README | Evidence file | Produced by |
|---|---|---|
| Corpus counts, provenance, gaps | `data/README.md`, `data/sources.json`, `data/processed/stats.json` | `doctor.py`, `ingest.py` |
| Citation accuracy, fact recall, refusal correctness, latency, cost | `docs/eval/*.json` + `docs/eval/latest.md` | `make eval` (Week 1+) |
| API contract | `docs/API.md` + generated types | `api-design` review |
| UI quality, a11y, responsive | `design-system/askdocs/MASTER.md` checklist | `ui-ux-pro-max` + Lighthouse/axe in Week 4 |
| Security posture | PR notes + `security-review` findings | `security-review` |
| Reproducibility on a new machine | this file + `AGENTS.md` bootstrap | `fetch_corpus.py`, `doctor.py` |

**Rule:** a number or a "done" claim that cannot name one of these artefacts does not go in the README.

## 4. Where the two toolchains disagree

ECC will happily approve a feature that is technically sound and visually poor; UI UX Pro Max will approve a beautiful screen over a broken contract. Neither alone is a gate — a change passes only when the code gate **and** the design checklist both pass. When they conflict, correctness and accessibility win, and the trade-off is recorded in `docs/DECISIONS.md`.
