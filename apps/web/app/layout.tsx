import type { Metadata } from "next";
import { EB_Garamond, JetBrains_Mono, Lato } from "next/font/google";
import "./globals.css";
import { SiteNav } from "@/components/site-nav";

// display: swap on all three faces - no invisible-text flash while they load.
const garamond = EB_Garamond({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-eb-garamond",
  display: "swap",
});
const lato = Lato({
  subsets: ["latin"],
  weight: ["300", "400", "700"],
  variable: "--font-lato",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "AskDocs — Indian tax law, with citations you can check",
  description:
    "Grounded question-answering over the Income-tax Act 1961, the Income-tax Act 2025, the 2026 Rules and the CGST Act. Every answer carries a section, a page and a vintage.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${garamond.variable} ${lato.variable} ${mono.variable}`}>
      <body className="min-h-dvh antialiased">
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <SiteNav />
        <main id="main" className="mx-auto w-full max-w-6xl px-4 pb-16 pt-8 sm:px-6">
          {children}
        </main>
        <footer className="border-t border-border">
          <div className="mx-auto w-full max-w-6xl px-4 py-6 text-xs text-muted-foreground sm:px-6">
            Informational only — not legal advice. Corpus vintage shown with each answer.
          </div>
        </footer>
      </body>
    </html>
  );
}
