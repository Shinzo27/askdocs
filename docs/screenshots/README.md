# Screenshots

Screenshots of the **running app**, not mock-ups. They exist so the project can be shown — in the README, in a portfolio card, in an interview — without asking anyone to run it first.

## What lands here

| File | Surface | Produced |
|---|---|---|
| `ask.png` | `/` answered question with inline `[n]` chips — **captured with the `echo` generator** (no model installed meets the latency budget on this 8 GB box; see the README's Week 2 section) | Week 2 |
| `ask-refused.png` | refusal state for an out-of-corpus question | Week 2 |
| `evidence-panel.png` | citation panel: doc · section · chapter · page · vintage | Week 3 |
| `corpus.png` | `/corpus` document + vintage + coverage table | Week 3 |
| `mobile-sheet.png` | evidence sheet at 375 px | Week 3 |
| `history.png` | `/history` with a saved conversation | Week 3 |

## Rules

1. Captured from the deployed or locally running app at the viewport named in the caption (1440 for desktop, 375 for mobile). A design preview from fixture data must be labelled `(design preview)` in the caption — the refusal panel especially, since it is the product's central behaviour and easy to fake convincingly.
2. Refreshed in Week 4 after the accessibility pass, so the images match what ships.
3. The 90-second recording lives in `docs/demo-script.md` (script) and the README (GIF); its frames come from the same run as these screenshots.

## Command sketch

```bash
npx playwright screenshot --viewport-size=1440,900 http://localhost:3000/ docs/screenshots/ask.png
npx playwright screenshot --viewport-size=375,812 http://localhost:3000/ docs/screenshots/mobile-sheet.png
```

Nothing here yet — the directory documents the protocol so the artefacts land in a known place instead of being scattered in chat.
