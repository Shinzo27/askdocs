# AskDocs — Design System (Master)

> **Protocol.** Building a page? Read this file, then check `pages/<page>.md` — if it exists, its rules **override** this file. Put deviations in a page file; do not edit Master for one screen.

**Provenance.** Generated with **UI UX Pro Max v2.0** (`--design-system --persist --tokens dtcg`, query: *"legal tax document research assistant citations chat trustworthy minimal serif"*, 2026-11-21), then **curated by hand**: the palette and type pairing were kept, the generator's generic "newsletter / content-first" page pattern was rejected, and the surfaces below were written for this product. Regeneration discards curation — it needs explicit approval and a diff review.

**Tokens.** `tokens.json` (W3C DTCG) is the machine-readable source for colour and font families. `font.mono` is a repo addition, not a generated value; keep it when regenerating.

---

## Product surfaces

| Surface | Job | Primary risk to design against |
|---|---|---|
| **Ask** (`/`) | one input, streamed answer with inline `[n]` markers | feeling like a chatbot toy instead of a legal tool |
| **Evidence panel** (right pane / sheet) | the cited section text, doc, vintage, page, "open in PDF" | losing the reader's place; unverifiable citations |
| **Corpus browser** (`/corpus`) | documents, vintages, sections, coverage — the honest inventory | implying completeness the corpus does not have |
| **Refusal state** | says "outside what I can verify", names what *is* covered | looking like an error, or looking like product failure |
| **Scope banner** | which Act and tax year the answer applies to | being dismissed and then forgotten |

Page pattern: **workspace, not landing page**. Split view, persistent navigation, no hero, no marketing section, no newsletter block. Density is `--space-md`-based; this is a reading and verification tool.

---

## Color

| Role | Hex | Token | Use |
|---|---|---|---|
| Primary | `#1E3A5F` | `--color-primary` | structure, links, citation markers, focus ring |
| On primary | `#FFFFFF` | `--color-on-primary` | text on primary |
| Secondary | `#334155` | `--color-secondary` | secondary UI, panel headers |
| Accent / CTA | `#B45309` | `--color-accent` | the single primary action per view ("Ask", "Open in PDF") |
| Background | `#F8FAFC` | `--color-background` | app canvas (paper, not white) |
| Foreground | `#0F172A` | `--color-foreground` | body text |
| Card | `#FFFFFF` | `--color-card` | answer surface, evidence panel |
| Muted | `#E9EEF5` | `--color-muted` | citation chips at rest, table stripes |
| Muted foreground | `#475569` | `--color-muted-foreground` | metadata, vintage text (4.5:1 on card) |
| Border | `#CBD5E1` | `--color-border` | panel dividers, table rules |
| Destructive | `#DC2626` | `--color-destructive` | real errors only — **never** a refusal |
| Ring | `#1E3A5F` | `--color-ring` | focus ring, 2 px + 2 px offset |

Refusal uses a `muted` surface + `accent` left rule, not red. Red means "something broke"; a refusal is a correct answer.

## Typography

| Role | Font | Size / line-height |
|---|---|---|
| H1 | EB Garamond 600 | 32 / 1.2 |
| H2 | EB Garamond 600 | 24 / 1.3 |
| Section title (evidence) | EB Garamond 600 | 20 / 1.35 |
| Body | Lato 400 | 16 / 1.6 (statute text 16 / 1.65) |
| UI label | Lato 600 | 13 / 1.4, `letter-spacing: 0.02em` |
| Section reference | JetBrains Mono / `ui-monospace` | 13–14, tabular figures |
| Footnote / vintage | Lato 400 | 12 / 1.5 — minimum size anywhere |

```css
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:wght@400;500;600;700&family=Lato:wght@300;400;700&display=swap');
```

Statute prose is set in the serif at a 68-character measure — the reader is checking an argument, not skimming a feed. Section numbers, page numbers and money are monospace so `80C` and `80CCD` never look alike.

## Spacing, radius, elevation

`--space-xs 4 · sm 8 · md 16 · lg 24 · xl 32 · 2xl 48 · 3xl 64`. Radius: 8 px controls, 12 px cards, 16 px sheets. Elevation: `sm` inline chips, `md` cards, `lg` drawers, `xl` modals — never elevation on hover alone (layout shift).

---

## Components

### Citation chip `[n]`
- A `<button>`, not a `<span>`: it opens the evidence panel.
- Mono 13 px, `--color-primary` on `--color-muted`, radius 6 px, hit area ≥ 44×44 px via padding.
- `aria-label="Source 1: Section 80C, Income-tax Act, 1961, page 330"`.
- Hover: background darkens one step. Focus: 2 px ring + offset, never removed. Active: panel opens and the corresponding passage scrolls into view with 200 ms smooth scroll (disabled under reduced-motion).
- Consecutive markers (`[1][2]`) keep a 4 px gap and never break across lines.

### Evidence panel
- Header block, always in this order: **doc title · Section · Chapter · page · vintage**. Not collapsible — it is the proof.
- Body: statute text, serif, 68ch max, `--color-foreground`; quoted table rows keep `--color-border` rules.
- Footer: `Open in PDF (p. 330) ↗` — accent, right-aligned, opens `#page=330` in a new tab with `rel="noopener"`.
- Empty state: "Ask a question, or open a section from the corpus browser."
- `<aside aria-labelledby="evidence-title">`; Escape closes and returns focus to the invoking chip.

### Streamed answer
- One `aria-live="polite"` region around the answer body; do not announce per token.
- Reserve the answer block height before tokens arrive (skeleton lines) so the composer never jumps.
- Typing indicator: 2 px caret, 1 s pulse, no reflow. Reduced motion → static caret.
- Selection and scroll position survive token arrival; never auto-scroll while the user is reading.
- Citations are inserted as chips when the `citation` event arrives, not fished out of the text client-side.

### Refusal card
- Muted surface, 3 px accent left rule, no warning icon, headline in plain language: *"I can't verify this from the documents I have."*
- Then: the reason in one sentence (`outside the corpus`, `tax year before 1 April 2026`, `no matching section`), the closest covered topic if one exists, and a `Browse what's covered` action.
- Never use destructive red, never show a fake citation, never make "try again" the primary action.

### Scope banner
- Persistent, non-dismissible, 12 px label + mono year, above the composer: `Answers apply to Tax Year 2026-27 · Income-tax Act, 2025`.
- On mixed-vintage answers it appears **inside** the answer header too, not only at page level.

### Composer
- 16 px minimum font (prevents iOS zoom), auto-grow to 6 lines, `Enter` sends and `Shift+Enter` newlines, `⌘/Ctrl+Enter` always sends.
- Busy state shows a `Stop` affordance, not a grey button: cancelling is a supported action.
- Character cap 500 shown as a counter only in the last 50 characters.

### Disclaimer
- Footer on every surface: `Informational only — not legal advice. Corpus vintage shown with each answer.` 12 px, `--color-muted-foreground`, 4.5:1 at 12 px: `#475569` on `#F8FAFC`, not lighter.

## Motion

150–250 ms, `ease-out` in / `ease-in` out, transform and opacity only. Never animate height or width. One exception: panel slide on mobile, 250 ms, transform only. `prefers-reduced-motion: reduce` disables the caret pulse, smooth scroll and panel slide (instant swap).

## Responsive

| Width | Layout |
|---|---|
| ≥ 1024 (1440 target) | two-pane: conversation 60 % / evidence 40 %, both scrollable, panel sticky |
| 768–1023 | conversation full width, evidence as right drawer 420 px |
| < 768 (375 target) | single column, evidence as full-height bottom sheet with drag handle and `Escape`/back support |
| print | evidence panel prints with page reference; answer prints without chips |

No horizontal scroll at any width; long section titles and section numbers wrap or truncate with an accessible full-value path (`title` + visible on focus), never clipped silently.

## Anti-patterns (do not ship)

- Emoji as icons; mixed icon families. Use Lucide, 1.5 px stroke, currentColor.
- Red for refusals, green for "correct", colour as the only signal of vintage or confidence.
- Hover-only affordances (tooltips as the only way to read a citation).
- Low-contrast metadata (the vintage line is the text a tax reader checks first).
- Layout-shifting hovers, instant state changes, autoplay motion.
- Chat bubbles, avatars and "typing…" personas — this is a research assistant, not a chat app.
- Infinite scroll in the evidence panel; a section must have a visible end.
- Anything that hides the disclaimer or the vintage behind a click.

## Pre-delivery checklist

- [ ] No emoji as icons; one icon set (Lucide), 1.5 px stroke
- [ ] Every citation chip is a real button with an `aria-label` naming section + page
- [ ] Focus visible on all interactive elements; focus order matches reading order
- [ ] Text contrast ≥ 4.5:1 (12 px metadata included); UI contrast ≥ 3:1
- [ ] Targets ≥ 44×44 px; `cursor: pointer` on all clickables
- [ ] `aria-live="polite"` on the answer; no per-token announcements
- [ ] Refusal state is visually distinct from an error and names the reason
- [ ] Scope banner + vintage visible in the answer header; disclaimer in the footer
- [ ] No layout shift while streaming; scroll position preserved
- [ ] `prefers-reduced-motion` verified (caret, smooth scroll, sheets)
- [ ] 375 / 768 / 1024 / 1440 checked; 200 % zoom and large-text reflow checked
- [ ] Light **and** dark mode contrast checked (dark mode lands in Week 3)
- [ ] Empty, loading, error and refusal states all designed, not just the happy path
- [ ] Evidence panel prints the page reference correctly
