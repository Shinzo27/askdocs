import { ArrowRight } from "lucide-react";

export default function AskPage() {
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <section aria-labelledby="ask-heading" className="flex flex-col gap-6">
        <div>
          <h1 id="ask-heading" className="font-heading text-3xl font-semibold text-primary">
            Ask a question about Indian tax law
          </h1>
          <p className="mt-3 max-w-prose text-secondary">
            Answers come only from six government documents, and every claim carries a citation
            you can open: document, section, page and vintage.
          </p>
        </div>

        {/* Scope banner: persistent and non-dismissible by design. */}
        <div
          className="flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-card border border-border bg-card px-4 py-3"
          role="note"
          aria-label="Which law these answers apply to"
        >
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Applies to
          </span>
          <span className="font-mono text-sm text-foreground">Tax Year 2026-27</span>
          <span className="text-muted-foreground" aria-hidden="true">
            ·
          </span>
          <span className="text-sm text-secondary">
            Income-tax Act, 2025 — earlier years fall under the Act of 1961
          </span>
        </div>

        <form className="flex flex-col gap-3" aria-describedby="composer-help">
          <label htmlFor="question" className="text-sm font-semibold text-foreground">
            Your question
          </label>
          <textarea
            id="question"
            name="question"
            rows={3}
            maxLength={500}
            disabled
            placeholder="How much can I deduct under section 80C for my child's tuition fees?"
            className="w-full resize-none rounded-card border border-border bg-card px-4 py-3 text-base text-foreground placeholder:text-muted-foreground disabled:cursor-not-allowed"
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p id="composer-help" className="text-xs text-muted-foreground">
              Streaming answers arrive in Week 2. Until then this composer is intentionally inert —
              no fake typing, no placeholder citations.
            </p>
            <button
              type="button"
              disabled
              className="inline-flex min-h-11 items-center gap-2 rounded-control bg-accent px-4 text-sm font-semibold text-on-accent opacity-60"
            >
              Ask
              <ArrowRight aria-hidden="true" size={16} strokeWidth={1.5} />
            </button>
          </div>
        </form>
      </section>

      <aside aria-labelledby="empty-heading" className="rounded-card border border-border bg-card p-6">
        <h2 id="empty-heading" className="font-heading text-xl font-semibold text-foreground">
          Nothing asked yet
        </h2>
        <p className="mt-3 text-sm text-secondary">
          When an answer cannot be grounded in the corpus, it is refused with a reason instead of
          guessed at. That refusal is the product&apos;s central honest behaviour, so it is designed
          before the happy path.
        </p>
        <ul className="mt-5 space-y-3 text-sm text-secondary">
          <li className="flex gap-3">
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
            <span>
              Every substantive claim carries a numbered marker — no marker, no claim.
            </span>
          </li>
          <li className="flex gap-3">
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
            <span>Citations name the Act and its vintage, because both Acts are in force.</span>
          </li>
          <li className="flex gap-3">
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
            <span>The corpus covers 11,069 section-tagged passages from 6 documents.</span>
          </li>
        </ul>
      </aside>
    </div>
  );
}
