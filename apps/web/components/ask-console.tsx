"use client";

/**
 * The Ask surface: one input, a streamed answer, and citation chips that open the
 * section they point at.
 *
 * Design rules this implements (design-system/askdocs/MASTER.md):
 *  - one `aria-live="polite"` region around the answer, never per-token announcements;
 *  - the composer shows a `Stop` affordance while streaming, because cancelling is
 *    a supported action, not a disabled button;
 *  - a citation is a real <button> with an aria-label naming section and page;
 *  - refusal is a muted surface with an accent rule, never destructive red.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUp, Loader2, Square, X } from "lucide-react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const MAX_QUESTION = 500;

type Citation = {
  marker: number;
  doc_id: string;
  section: string | null;
  section_title: string | null;
  chapter: string | null;
  page: number | null;
  vintage: string | null;
  rerank_score?: number;
};

type Usage = {
  prompt_tokens: number;
  completion_tokens: number;
  provider: string;
  model: string;
  cost_inr: number;
  latency_ms: { retrieve: number; rerank: number; first_token: number; total: number };
};

type Answer = {
  text: string;
  citations: Citation[];
  usage: Usage | null;
  streaming: boolean;
  refused: boolean;
  reason: string | null;
  citationValid: boolean | null;
  error: string | null;
  retrievedSections?: string[];
};

type Section = {
  doc_title: string;
  section: string;
  section_title: string | null;
  chapter: string | null;
  page: number | null;
  vintage: string | null;
  text: string;
};

const EMPTY: Answer = {
  text: "",
  citations: [],
  usage: null,
  streaming: false,
  refused: false,
  reason: null,
  citationValid: null,
  error: null,
};

export function AskConsole() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer>(EMPTY);
  const [asked, setAsked] = useState<string | null>(null);
  const [open, setOpen] = useState<{ marker: number; section: Section | null; error: boolean } | null>(
    null,
  );
  const abort = useRef<AbortController | null>(null);
  const answerRef = useRef<HTMLDivElement | null>(null);
  const chipRefs = useRef<Record<number, HTMLButtonElement | null>>({});

  const ask = useCallback(async () => {
    const q = question.trim();
    if (!q || answer.streaming) return;
    abort.current?.abort();
    abort.current = new AbortController();
    setAsked(q);
    setOpen(null);
    setAnswer({ ...EMPTY, streaming: true });

    try {
      const response = await fetch(`${API}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q, stream: true }),
        credentials: "include", // the session cookie carries conversation history
        signal: abort.current.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`The API answered ${response.status}.`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are separated by a blank line.
        let cut = buffer.indexOf("\n\n");
        while (cut !== -1) {
          const frame = buffer.slice(0, cut);
          buffer = buffer.slice(cut + 2);
          cut = buffer.indexOf("\n\n");

          const eventLine = frame.split("\n").find((l) => l.startsWith("event: "));
          const dataLine = frame.split("\n").find((l) => l.startsWith("data: "));
          if (!eventLine || !dataLine) continue;
          const type = eventLine.slice(7).trim();
          const data = JSON.parse(dataLine.slice(6));

          setAnswer((prev) => {
            if (type === "token") return { ...prev, text: prev.text + data.text };
            if (type === "retrieval") return { ...prev, retrievedSections: data.sections };
            if (type === "citation")
              return { ...prev, citations: [...prev.citations, data as Citation] };
            if (type === "usage") return { ...prev, usage: data as Usage };
            if (type === "done")
              return {
                ...prev,
                streaming: false,
                refused: Boolean(data.refused),
                reason: data.reason ?? null,
                citationValid: data.citation_valid ?? null,
                // A refusal's text arrives as the token stream, so nothing to add.
              };
            if (type === "error")
              return { ...prev, streaming: false, error: data.message ?? "Generation failed." };
            return prev;
          });
        }
      }
    } catch (error) {
      if ((error as Error).name === "AbortError") {
        setAnswer((prev) => ({ ...prev, streaming: false }));
        return;
      }
      setAnswer((prev) => ({
        ...prev,
        streaming: false,
        error: (error as Error).message,
      }));
    }
  }, [answer.streaming, question]);

  const stop = useCallback(() => {
    abort.current?.abort();
    setAnswer((prev) => ({ ...prev, streaming: false }));
  }, []);

  const openCitation = useCallback(async (citation: Citation) => {
    setOpen({ marker: citation.marker, section: null, error: false });
    try {
      const response = await fetch(
        `${API}/sections/${citation.doc_id}/${encodeURIComponent(citation.section ?? "")}`,
        { credentials: "include" },
      );
      if (!response.ok) throw new Error("section missing");
      const section = (await response.json()) as Section;
      setOpen({ marker: citation.marker, section, error: false });
    } catch {
      setOpen({ marker: citation.marker, section: null, error: true });
    }
  }, []);

  const closePanel = useCallback(() => {
    const marker = open?.marker;
    setOpen(null);
    if (marker) chipRefs.current[marker]?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closePanel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, closePanel]);

  const busy = answer.streaming;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)] lg:items-start">
      <section aria-labelledby="ask-heading" className="flex flex-col gap-6">
        <div>
          <h1 id="ask-heading" className="font-heading text-3xl font-semibold text-primary">
            Ask a question about Indian tax law
          </h1>
          <p className="mt-3 max-w-prose text-secondary">
            Answers come only from the documents in the corpus, and every claim carries a citation
            you can open: document, section, page and vintage.
          </p>
        </div>

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

        <form
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void ask();
          }}
          aria-describedby="composer-help"
        >
          <label htmlFor="question" className="text-sm font-semibold text-foreground">
            Your question
          </label>
          <textarea
            id="question"
            name="question"
            rows={3}
            maxLength={MAX_QUESTION}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              const submit = event.key === "Enter" && (event.metaKey || event.ctrlKey || !event.shiftKey);
              if (submit) {
                event.preventDefault();
                void ask();
              }
            }}
            placeholder="How much can I deduct under section 80C for my child's tuition fees?"
            className="w-full resize-none rounded-card border border-border bg-card px-4 py-3 text-base text-foreground placeholder:text-muted-foreground"
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p id="composer-help" className="text-xs text-muted-foreground">
              Enter sends · Shift+Enter for a new line · answers are informational only
              {question.length > MAX_QUESTION - 50 ? ` · ${MAX_QUESTION - question.length} left` : ""}
            </p>
            <div className="flex items-center gap-2">
              {busy ? (
                <button
                  type="button"
                  onClick={stop}
                  className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-control border border-border bg-card px-4 text-sm font-semibold text-foreground transition-colors duration-150 hover:bg-muted"
                >
                  <Square aria-hidden="true" size={14} strokeWidth={1.5} />
                  Stop
                </button>
              ) : null}
              <button
                type="submit"
                disabled={busy || question.trim().length < 3}
                className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-control bg-accent px-4 text-sm font-semibold text-on-accent transition-colors duration-150 hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-60"
              >
                {busy ? (
                  <Loader2 aria-hidden="true" size={16} strokeWidth={1.5} className="animate-spin" />
                ) : null}
                Ask
                <ArrowUp aria-hidden="true" size={16} strokeWidth={1.5} />
              </button>
            </div>
          </div>
        </form>

        {asked ? (
          <article className="rounded-card border border-border bg-card p-6">
            <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2 border-b border-border pb-3">
              <h2 className="font-heading text-lg font-semibold text-foreground">{asked}</h2>
              {answer.usage ? (
                <span className="font-mono text-xs text-muted-foreground">
                  {answer.usage.provider}/{answer.usage.model} · {answer.usage.latency_ms.total} ms
                </span>
              ) : null}
            </header>

            {answer.error ? (
              <p className="text-sm text-destructive" role="alert">
                {answer.error} The answer could not be generated — nothing was invented in its place.
              </p>
            ) : null}

            {answer.refused ? (
              <div className="rounded-r-control border-l-[3px] border-accent bg-muted px-4 py-3">
                <p className="text-sm font-semibold text-foreground">
                  I can&apos;t verify this from the documents I have.
                </p>
                <div
                  className="statute-measure mt-2 whitespace-pre-line text-sm text-secondary"
                  aria-live="polite"
                >
                  {answer.text}
                </div>
                <a
                  href="/corpus"
                  className="mt-3 inline-flex min-h-11 items-center text-sm font-semibold text-accent underline-offset-4 hover:underline"
                >
                  Browse what&apos;s covered
                </a>
              </div>
            ) : (
              <div aria-live="polite" aria-atomic="false" ref={answerRef}>
                <div className="statute-measure whitespace-pre-line text-base text-foreground">
                  {answer.text}
                  {busy ? (
                    <span
                      aria-hidden="true"
                      className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-primary align-text-bottom motion-reduce:animate-none"
                    />
                  ) : null}
                </div>

                {answer.citations.length > 0 ? (
                  <ul className="mt-5 flex flex-wrap gap-2" aria-label="Sources for this answer">
                    {answer.citations.map((citation) => (
                      <li key={citation.marker}>
                        <button
                          type="button"
                          ref={(node) => {
                            chipRefs.current[citation.marker] = node;
                          }}
                          onClick={() => void openCitation(citation)}
                          aria-label={`Source ${citation.marker}: Section ${
                            citation.section ?? "unknown"
                          }, ${citation.doc_id}, page ${citation.page ?? "n/a"}`}
                          aria-expanded={open?.marker === citation.marker}
                          className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-control bg-muted px-3 font-mono text-xs text-primary transition-colors duration-150 hover:bg-border"
                        >
                          <span className="tabular-nums">[{citation.marker}]</span>
                          <span className="font-body">
                            §{citation.section} · {citation.doc_id.replace("it-act-", "")} p.
                            {citation.page ?? "—"}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : !busy ? (
                  <p className="mt-4 text-xs text-muted-foreground">
                    No citations were resolved for this answer, so it is not shown as verified
                    {answer.citationValid === false ? " (citation validation failed)." : "."}
                  </p>
                ) : null}
              </div>
            )}

            {answer.usage ? (
              <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-1 border-t border-border pt-3 text-xs text-muted-foreground sm:grid-cols-4">
                <div>
                  <dt className="inline">retrieve </dt>
                  <dd className="inline font-mono tabular-nums">
                    {answer.usage.latency_ms.retrieve} ms
                  </dd>
                </div>
                <div>
                  <dt className="inline">rerank </dt>
                  <dd className="inline font-mono tabular-nums">
                    {answer.usage.latency_ms.rerank} ms
                  </dd>
                </div>
                <div>
                  <dt className="inline">first token </dt>
                  <dd className="inline font-mono tabular-nums">
                    {answer.usage.latency_ms.first_token} ms
                  </dd>
                </div>
                <div>
                  <dt className="inline">cost </dt>
                  <dd className="inline font-mono tabular-nums">₹{answer.usage.cost_inr}</dd>
                </div>
              </dl>
            ) : null}
          </article>
        ) : null}
      </section>

      <aside
        aria-labelledby={open ? "evidence-title" : "empty-heading"}
        aria-live="polite"
        className="rounded-card border border-border bg-card p-6"
      >
        {open ? (
          <>
            <div className="flex items-start justify-between gap-3">
              <h2 id="evidence-title" className="font-heading text-xl font-semibold text-foreground">
                {open.section?.section_title ?? "Section"}
              </h2>
              <button
                type="button"
                onClick={closePanel}
                aria-label="Close the source panel"
                className="inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-control text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-foreground"
              >
                <X aria-hidden="true" size={18} strokeWidth={1.5} />
              </button>
            </div>

            {open.error ? (
              <p className="mt-3 text-sm text-secondary">
                This section is not individually anchored in the corpus — the honest gap documented
                on the corpus page.
              </p>
            ) : open.section ? (
              <>
                <dl className="mt-3 space-y-1 text-xs text-muted-foreground">
                  <div>
                    <dt className="inline">document </dt>
                    <dd className="inline text-foreground">{open.section.doc_title}</dd>
                  </div>
                  <div>
                    <dt className="inline">section </dt>
                    <dd className="inline font-mono text-foreground">{open.section.section}</dd>
                    {open.section.chapter ? (
                      <>
                        <dt className="inline"> · chapter </dt>
                        <dd className="inline font-mono text-foreground">{open.section.chapter}</dd>
                      </>
                    ) : null}
                    {open.section.page ? (
                      <>
                        <dt className="inline"> · page </dt>
                        <dd className="inline font-mono text-foreground">{open.section.page}</dd>
                      </>
                    ) : null}
                  </div>
                  <div>
                    <dt className="inline">vintage </dt>
                    <dd className="inline text-foreground">{open.section.vintage}</dd>
                  </div>
                </dl>
                <div className="statute-measure mt-4 max-h-[28rem] overflow-y-auto whitespace-pre-line border-t border-border pt-4 text-sm text-foreground">
                  {open.section.text}
                </div>
              </>
            ) : (
              <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 aria-hidden="true" size={14} strokeWidth={1.5} className="animate-spin" />
                Opening the section…
              </p>
            )}
          </>
        ) : (
          <>
            <h2 id="empty-heading" className="font-heading text-xl font-semibold text-foreground">
              Sources appear here
            </h2>
            <p className="mt-3 text-sm text-secondary">
              Ask a question, then open any <span className="font-mono text-xs">[n]</span> chip to
              read the section it cites — document, section, page and vintage first.
            </p>
            <ul className="mt-5 space-y-3 text-sm text-secondary">
              <li className="flex gap-3">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
                <span>Every claim carries a numbered marker; no marker, no claim.</span>
              </li>
              <li className="flex gap-3">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
                <span>If the corpus cannot support an answer, you get a refusal with a reason.</span>
              </li>
            </ul>
          </>
        )}
      </aside>
    </div>
  );
}
