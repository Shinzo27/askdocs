export const metadata = { title: "About — AskDocs" };

export default function AboutPage() {
  return (
    <div className="flex flex-col gap-8">
      <header>
        <h1 className="font-heading text-3xl font-semibold text-primary">About</h1>
        <p className="mt-3 max-w-prose text-secondary">
          AskDocs answers questions about Indian income-tax and GST law from official documents only,
          and cites the section, page and vintage behind every claim.
        </p>
      </header>

      <section aria-labelledby="disclaimer" className="rounded-card border border-border bg-card p-6">
        <h2 id="disclaimer" className="font-heading text-xl font-semibold text-foreground">
          Informational only, not legal advice
        </h2>
        <p className="mt-3 max-w-prose text-sm text-secondary">
          This is a research aid over statute text. It does not know your facts, cannot give advice,
          and does not replace a chartered accountant. Where the corpus cannot support an answer, the
          assistant refuses and says why.
        </p>
      </section>

      <section aria-labelledby="vintage" className="rounded-card border border-border bg-card p-6">
        <h2 id="vintage" className="font-heading text-xl font-semibold text-foreground">
          Two Acts are in force
        </h2>
        <p className="mt-3 max-w-prose text-sm text-secondary">
          The Income-tax Act, 2025 governs income from 1 April 2026. Every tax year that began
          earlier — returns, assessments, appeals — continues under the Income-tax Act, 1961, which
          is why both are in the corpus and why each answer names the vintage it used.
        </p>
      </section>

      <section aria-labelledby="eval" className="rounded-card border border-border bg-card p-6">
        <h2 id="eval" className="font-heading text-xl font-semibold text-foreground">
          How quality is measured
        </h2>
        <p className="mt-3 max-w-prose text-sm text-secondary">
          A hand-written golden set of 40 questions scores citation accuracy, fact recall, refusal
          correctness, latency and cost. Reports are published with their misses, and each one quotes
          the corpus hash it ran against — numbers from different corpora are not comparable.
        </p>
      </section>
    </div>
  );
}
