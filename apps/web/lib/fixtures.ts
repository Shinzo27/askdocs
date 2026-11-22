/**
 * Fixture corpus data for the Week 1 shell.
 *
 * Deliberately a file, not a fetch: the shell has to be reviewable before the
 * API exists. Every number here is copied from data/processed/stats.json and is
 * labelled as fixture in the UI until /corpus reads GET /corpus/stats (Week 3).
 */
export type CorpusDocument = {
  docId: string;
  title: string;
  vintage: string;
  appliesTo: string;
  pages: number | null;
  sections: number;
  chunks: number;
};

export const CORPUS: CorpusDocument[] = [
  {
    docId: "it-act-2025",
    title: "Income-tax Act, 2025",
    vintage: "Act No. 30 of 2025, as amended by Finance Act, 2026",
    appliesTo: "Tax Year 2026-27 onwards",
    pages: 687,
    sections: 529,
    chunks: 1762,
  },
  {
    docId: "it-rules-2026",
    title: "Income-tax Rules, 2026",
    vintage: "notified 20 March 2026, in force 1 April 2026",
    appliesTo: "Tax Year 2026-27 onwards",
    pages: 977,
    sections: 327,
    chunks: 2670,
  },
  {
    docId: "it-act-1961",
    title: "Income-tax Act, 1961",
    vintage: "consolidated up to Finance Act, 2021",
    appliesTo: "AY 2026-27 and earlier",
    pages: 956,
    sections: 768,
    chunks: 3852,
  },
  {
    docId: "cgst-act-2017",
    title: "Central Goods and Services Tax Act, 2017",
    vintage: "as on 01.08.2021",
    appliesTo: "GST — ongoing",
    pages: null,
    sections: 168,
    chunks: 579,
  },
  {
    docId: "cgst-rules-2017",
    title: "Central Goods and Services Tax Rules, 2017",
    vintage: "as on 30.12.2017 (base rules)",
    appliesTo: "GST — ongoing",
    pages: null,
    sections: 176,
    chunks: 889,
  },
];

export const CORPUS_TOTALS = {
  documents: CORPUS.length,
  chunks: CORPUS.reduce((sum, d) => sum + d.chunks, 0),
  sections: CORPUS.reduce((sum, d) => sum + d.sections, 0),
};
