import { History } from "lucide-react";

export const metadata = { title: "History — AskDocs" };

export default function HistoryPage() {
  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="font-heading text-3xl font-semibold text-primary">History</h1>
        <p className="mt-3 max-w-prose text-secondary">
          Conversations are tied to an anonymous session cookie — no account, no email. Nothing is
          shared between sessions, and the share link is read-only.
        </p>
      </header>

      <div className="flex flex-col items-start gap-4 rounded-card border border-dashed border-border bg-card p-8">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-primary">
          <History aria-hidden="true" size={20} strokeWidth={1.5} />
        </span>
        <div>
          <h2 className="font-heading text-xl font-semibold text-foreground">No conversations yet</h2>
          <p className="mt-2 max-w-prose text-sm text-secondary">
            History lands in Week 3 with the citation viewer. Until then this page exists so the
            empty state is designed before the feature is built — the state a stranger sees first is
            the one worth getting right.
          </p>
        </div>
        <a
          href="/"
          className="inline-flex min-h-11 items-center rounded-control bg-primary px-4 text-sm font-semibold text-on-primary transition-colors duration-150 hover:bg-secondary"
        >
          Ask the first question
        </a>
      </div>
    </div>
  );
}
