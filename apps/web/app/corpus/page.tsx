import { CORPUS, CORPUS_TOTALS } from "@/lib/fixtures";

export const metadata = { title: "Corpus — AskDocs" };

export default function CorpusPage() {
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-heading text-3xl font-semibold text-primary">What is covered</h1>
        <p className="mt-3 max-w-prose text-secondary">
          Six government documents, {CORPUS_TOTALS.sections.toLocaleString("en-IN")} sections and{" "}
          {CORPUS_TOTALS.chunks.toLocaleString("en-IN")} passages. Gaps are stated, not implied away.
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Fixture data — this table is wired to <code className="font-mono">GET /corpus/stats</code>{" "}
          in Week 3, so nothing here is hardcoded in the shipped surface.
        </p>
      </header>

      <div className="overflow-x-auto rounded-card border border-border bg-card">
        <table className="w-full min-w-[46rem] border-collapse text-left text-sm">
          <caption className="sr-only">
            Documents in the corpus, with vintage, applicable tax years, sections and chunks
          </caption>
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
              <th scope="col" className="px-4 py-3 font-semibold">
                Document
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                Vintage
              </th>
              <th scope="col" className="px-4 py-3 font-semibold">
                Applies to
              </th>
              <th scope="col" className="px-4 py-3 text-right font-semibold">
                Sections
              </th>
              <th scope="col" className="px-4 py-3 text-right font-semibold">
                Chunks
              </th>
            </tr>
          </thead>
          <tbody>
            {CORPUS.map((doc, index) => (
              <tr
                key={doc.docId}
                className={index % 2 === 1 ? "border-t border-border bg-muted/40" : "border-t border-border"}
              >
                <th scope="row" className="px-4 py-3 font-normal">
                  <span className="block font-semibold text-foreground">{doc.title}</span>
                  <span className="font-mono text-xs text-muted-foreground">{doc.docId}</span>
                </th>
                <td className="px-4 py-3 text-secondary">{doc.vintage}</td>
                <td className="px-4 py-3 font-mono text-xs text-secondary">{doc.appliesTo}</td>
                <td className="px-4 py-3 text-right font-mono tabular-nums text-foreground">
                  {doc.sections}
                </td>
                <td className="px-4 py-3 text-right font-mono tabular-nums text-foreground">
                  {doc.chunks.toLocaleString("en-IN")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <section className="rounded-card border border-border bg-card p-6" aria-labelledby="gaps-heading">
        <h2 id="gaps-heading" className="font-heading text-xl font-semibold text-foreground">
          Known gaps
        </h2>
        <ul className="mt-3 space-y-2 text-sm text-secondary">
          <li>
            23 of 536 sections of the 2025 Act are not individually anchored; they are reported as{" "}
            <code className="font-mono text-xs">sections_unparsed</code>, not guessed at.
          </li>
          <li>CBDT circulars are not in the corpus — “why” questions are answered from statute only.</li>
          <li>
            The 1961 Act copy is consolidated to Finance Act 2021, so later amendments are not
            reflected. That is why every answer states its vintage.
          </li>
        </ul>
      </section>
    </div>
  );
}
