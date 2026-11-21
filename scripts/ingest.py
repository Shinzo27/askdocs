#!/usr/bin/env python3
"""
AskDocs ingestion: raw PDFs / CSV / HTML -> normalised JSONL chunks.

Design notes
------------
- PDFs are converted with poppler's `pdftotext -layout`, which preserves
  indentation a lot better than pure PyPDF extraction on Indian statute PDFs.
- Page breaks (\f) are kept so every chunk can cite a page.
- Statute PDFs mark sections as "12A. Title of section" at the start of a line.
  We split on those, so a retrieved chunk maps to a citable section, not an
  arbitrary 1000-character window.
- Long sections (> MAX_CHARS) are split on paragraph boundaries with overlap,
  and every sub-chunk keeps the parent section number.
- Nothing here needs network access: it reads data/raw/ and writes
  data/processed/.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"

MAX_CHARS = 1200
OVERLAP = 150
MIN_CHUNK = 120  # drop page furniture / stray headers

# "12A. Title" / "2. Definitions." at line start, up to 8 spaces of indent.
# Statute PDFs prefix amended sections with footnote markers, e.g. "4[80C. ...",
# so an optional leading "N[" or "*" must be tolerated or whole sections vanish.
SECTION_RE = re.compile(r"^\s{0,10}(?:\d{1,2}\[\s*|\*+\s*)?(\d{1,3}[A-Z]{0,2})\.\s+([A-Z\[(][^\n]{2,120})")
# Chapter / schedule markers are useful metadata even though they don't split
CHAPTER_RE = re.compile(r"^\s*(CHAPTER\s+[IVXL]+|SCHEDULE\s+[IVXL]+[A-Z]?)\b")


@dataclass
class Chunk:
    id: str
    doc_id: str
    doc_title: str
    doc_type: str          # act | rules | faq | form | commentary
    section: str | None
    section_title: str | None
    chapter: str | None
    page: int
    chunk_index: int
    text: str
    chars: int


def pdf_to_pages(path: Path) -> list[str]:
    """Return one string per PDF page."""
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            capture_output=True, check=True,
        ).stdout.decode("utf-8", errors="ignore")
    except FileNotFoundError:
        sys.exit("pdftotext not found - install poppler-utils")
    except subprocess.CalledProcessError as exc:
        print(f"  ! pdftotext failed on {path.name}: {exc}", file=sys.stderr)
        return []
    return [p for p in out.split("\f") if p.strip()]


def split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts or [text.strip()]


def pack(paragraphs: list[str]) -> list[str]:
    """Greedy pack paragraphs into <= MAX_CHARS windows with tail overlap."""
    chunks, buf = [], ""
    for para in paragraphs:
        if len(para) > MAX_CHARS:  # a single giant paragraph
            if buf:
                chunks.append(buf)
                buf = ""
            start = 0
            while start < len(para):
                chunks.append(para[start:start + MAX_CHARS])
                start += MAX_CHARS - OVERLAP
            continue
        if len(buf) + len(para) + 1 <= MAX_CHARS:
            buf = f"{buf}\n{para}" if buf else para
        else:
            chunks.append(buf)
            buf = (buf[-OVERLAP:] + "\n" + para).strip() if buf else para
    if buf:
        chunks.append(buf)
    return [c.strip() for c in chunks if len(c.strip()) >= MIN_CHUNK]


def is_toc_page(page: str) -> bool:
    """Detect 'ARRANGEMENT OF SECTIONS' style table-of-contents pages.

    TOC pages list one short section heading per line; body pages wrap long
    prose. Counting section-regex hits alone over-matches body pages (which
    reference many sections inline), so require short lines too.
    """
    lines = [ln for ln in page.splitlines() if ln.strip()]
    if not lines:
        return False
    hits = sum(1 for ln in lines if SECTION_RE.match(ln))
    long_lines = sum(1 for ln in lines if len(ln.strip()) > 95)
    if "ARRANGEMENT OF SECTIONS" in page or page.lstrip().startswith("CONTENTS"):
        return hits >= 5
    return hits >= 8 and long_lines <= len(lines) * 0.2


def ingest_statute(path: Path, doc_id: str, title: str, doc_type: str) -> list[Chunk]:
    pages = pdf_to_pages(path)
    if not pages:
        return []

    rows: list[tuple[str | None, str | None, str | None, int, str]] = []
    cur_sec: str | None = None
    cur_title: str | None = None
    cur_chap: str | None = None

    for page_no, page in enumerate(pages, start=1):
        if is_toc_page(page):
            continue
        for line in page.splitlines():
            stripped = line.strip()
            if not stripped:
                rows.append((cur_sec, cur_title, cur_chap, page_no, ""))
                continue
            if CHAPTER_RE.match(stripped):
                cur_chap = stripped.split()[1] if len(stripped.split()) > 1 else stripped
                rows.append((cur_sec, cur_title, cur_chap, page_no, stripped))
                continue
            m = SECTION_RE.match(line)
            # Guard against numbered lists inside a section (e.g. "(a) 12. ...")
            if m and not stripped.startswith("(") and len(m.group(2).split()) >= 2:
                cur_sec, cur_title = m.group(1), m.group(2).strip().rstrip(".")
            rows.append((cur_sec, cur_title, cur_chap, page_no, stripped))

    # group consecutive rows by section
    groups: list[dict] = []
    for sec, sec_title, chap, page, line in rows:
        if groups and groups[-1]["section"] == sec:
            groups[-1]["lines"].append(line)
        else:
            groups.append({"section": sec, "section_title": sec_title,
                           "chapter": chap, "page": page, "lines": [line]})

    chunks: list[Chunk] = []
    for g in groups:
        body = "\n".join(g["lines"]).strip()
        if len(body) < MIN_CHUNK:
            continue
        for i, piece in enumerate(pack(split_paragraphs(body))):
            chunks.append(Chunk(
                id=f"{doc_id}:{g['section'] or 'x'}:{i}",
                doc_id=doc_id, doc_title=title, doc_type=doc_type,
                section=g["section"], section_title=g["section_title"],
                chapter=g["chapter"], page=g["page"], chunk_index=i,
                text=piece, chars=len(piece),
            ))
    return chunks


def ingest_faqs(path: Path) -> list[Chunk]:
    """Q&A rows -> one chunk each. Eval/answer-shape source, not statute text."""
    chunks: list[Chunk] = []
    with path.open(encoding="utf-8", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            q = (row.get("Query ") or row.get("Query") or "").strip()
            a = (row.get("Answer") or "").strip()
            if not q or not a:
                continue
            text = f"Q: {q}\nA: {a}"
            for i, piece in enumerate(pack(split_paragraphs(text))):
                chunks.append(Chunk(
                    id=f"faq:{row.get('ids', len(chunks))}:{i}",
                    doc_id="faq-cbdt", doc_title="CBDT taxpayer FAQs",
                    doc_type="faq", section=None, section_title=None, chapter=None,
                    page=0, chunk_index=i, text=piece, chars=len(piece),
                ))
    return chunks


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {p.name: {"doc_id": d, "title": t, "type": k} for p, d, t, k in DOCS}
    all_chunks: list[Chunk] = []

    for path, doc_id, title, doc_type in DOCS:
        if not path.exists():
            print(f"- skip {path.name} (missing)")
            continue
        print(f"+ {path.name} ...", end=" ", flush=True)
        produced = ingest_faqs(path) if path.suffix == ".csv" else ingest_statute(path, doc_id, title, doc_type)
        print(f"{len(produced)} chunks")
        all_chunks.extend(produced)

    with (OUT / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for c in all_chunks:
            fh.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")

    by_doc: dict[str, int] = {}
    for c in all_chunks:
        by_doc[c.doc_id] = by_doc.get(c.doc_id, 0) + 1
    sections = {c.doc_id for c in all_chunks if c.section}
    stats = {
        "documents": manifest,
        "chunks": len(all_chunks),
        "chunks_by_doc": by_doc,
        "docs_with_sections": sorted(sections),
        "total_chars": sum(c.chars for c in all_chunks),
        "avg_chars": round(sum(c.chars for c in all_chunks) / max(len(all_chunks), 1)),
        "max_chars": max((c.chars for c in all_chunks), default=0),
    }
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps(stats, indent=2))


DOCS = [
    (RAW / "it_act_thc.pdf", "it-act-1961", "Income-tax Act, 1961", "act"),
    (RAW / "cgst_act.pdf", "cgst-act-2017", "Central Goods and Services Tax Act, 2017", "act"),
    (RAW / "cgst_rules.pdf", "cgst-rules-2017", "Central Goods and Services Tax Rules, 2017", "rules"),
    (RAW / "tax_faqs.csv", "faq-cbdt", "CBDT taxpayer FAQs", "faq"),
]

if __name__ == "__main__":
    main()
