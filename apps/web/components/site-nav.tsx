"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BookOpen, History, Info, MessageSquareText } from "lucide-react";

const ROUTES = [
  { href: "/", label: "Ask", Icon: MessageSquareText },
  { href: "/corpus", label: "Corpus", Icon: BookOpen },
  { href: "/history", label: "History", Icon: History },
  { href: "/about", label: "About", Icon: Info },
] as const;

export function SiteNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
      <div className="mx-auto flex w-full max-w-6xl items-center gap-6 px-4 py-3 sm:px-6">
        <Link
          href="/"
          className="font-heading text-xl font-semibold tracking-tight text-primary"
          aria-label="AskDocs home"
        >
          AskDocs
        </Link>

        <nav aria-label="Primary" className="flex items-center gap-1">
          {ROUTES.map(({ href, label, Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-11 items-center gap-2 rounded-control px-3 text-sm transition-colors duration-150 ${
                  active
                    ? "bg-muted font-semibold text-primary"
                    : "text-secondary hover:bg-muted hover:text-primary"
                }`}
              >
                <Icon aria-hidden="true" size={16} strokeWidth={1.5} />
                <span>{label}</span>
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
