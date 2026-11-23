#!/usr/bin/env python3
"""
AskDocs ingestion: raw PDFs / CSV -> normalised JSONL chunks.

Design notes
------------
- Documents are described in `data/manifest.json`, not hardcoded here. Adding a
  document is one manifest entry; an unmapped PDF is still ingested (inferred
  metadata + a loud warning) so a drop never silently does nothing.
- Two extraction modes, because Indian statute PDFs come in two shapes:
    * `layout` (pdftotext -layout) keeps indentation, which the thc.nic.in copy
      of the 1961 Act needs;
    * `raw` keeps reading order, which the two-column gazette PDFs of the 2025
      Act and the 2026 Rules need - with -layout their section numbers scatter
      and 536 sections collapse into ~170.
- Two header styles, because the header itself moved:
    * `inline` -> "80C. Deduction in respect of life insurance premia..."
    * `above`  -> title on one line, "1. (1) This Act may be called..." below
  Style is declared per document; an unknown document is auto-detected by
  counting distinct section numbers under each style and keeping the winner.
- Page breaks (\\f) are kept so every chunk can cite a page.
- Long sections (> MAX_CHARS) are split on paragraph boundaries with overlap,
  and every sub-chunk keeps the parent section number.
- Nothing here needs network access: it reads data/raw/ and writes
  data/processed/.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
MANIFEST = ROOT / "data" / "manifest.json"

MAX_CHARS = 1200
OVERLAP = 150
MIN_CHUNK = 120  # drop page furniture / stray headers

# "12A. Title" / "2. Definitions." at line start, up to 10 spaces of indent.
# Statute PDFs prefix amended sections with footnote markers, e.g. "4[80C. ...",
# so an optional leading "N[" or "*" must be tolerated or whole sections vanish.
# The digit is optional: poppler 24.02 (-layout) lifts the superscript onto the
# line above and prints a bare "[80C." - requiring it dropped 279 sections of
# the 1961 Act on Linux while the same PDF parsed fine on the Windows build.
SECTION_RE = re.compile(r"^\s{0,10}(?:\d{0,2}\[\s*|\*+\s*)?(\d{1,3}[A-Z]{0,2})\.\s+([A-Z\[(][^\n]{2,120})")
# Header style "above": a title line, then "<num>. (1) body..." beneath it.
# The 2025 Act prints "9.(1)" with no space after the dot, so whitespace cannot
# be required - only that the number is followed by space, end of line or "(".
NUM_HEAD_RE = re.compile(r"^\s{0,6}(\d{1,3}[A-Z]{0,2})\.(?=\s|$|\()")
# Part markers in the 2025 Act: "B.--Salaries"
PART_RE = re.compile(r"^([A-Z])\.--([A-Z][^|]{2,60})$")
# A plausible section title: capitalised, ends with a full stop, no table pipes.
TITLE_LINE_RE = re.compile(r"^[A-Z][^|]{2,116}\.$")
# Chapter / schedule markers are useful metadata even though they don't split
CHAPTER_RE = re.compile(r"^\s*(CHAPTER\s+[IVXL]+|SCHEDULE\s+[IVXL]+[A-Z]?)\b")


@dataclass
class Chunk:
    id: str
    doc_id: str
    doc_title: str
    doc_type: str          # act | rules | faq | form | commentary
    vintage: str | None
    applies_to_ay: str | None
    section: str | None
    section_title: str | None
    chapter: str | None
    page: int
    chunk_index: int
    text: str
    chars: int


# --------------------------------------------------------------------------- #
# extraction
# --------------------------------------------------------------------------- #

def pdf_to_pages(path: Path, mode: str = "layout") -> list[str]:
    """Return one string per PDF page, extracted with pdftotext (-layout/-raw)."""
    args = ["pdftotext"]
    if mode == "layout":
        args.append("-layout")
    elif mode == "raw":
        args.append("-raw")
    try:
        out = subprocess.run(
            [*args, str(path), "-"], capture_output=True, check=True
        ).stdout.decode("utf-8", errors="ignore")
    except FileNotFoundError:
        sys.exit("pdftotext not found - install poppler-utils")
    except subprocess.CalledProcessError as exc:
        print(f"  ! pdftotext failed on {path.name}: {exc}", file=sys.stderr)
        return []
    return [p for p in out.split("\f") if p.strip()]


def pdftotext_version() -> str | None:
    """Poppler build that produced the text, e.g. "24.02.0".

    Recorded in stats.json because different poppler builds lay the same PDF
    out differently, so chunk counts are only comparable within one build.
    """
    try:
        res = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    m = re.search(r"version\s+(\S+)", res.stderr + res.stdout)
    return m.group(1) if m else None


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


def is_toc_page(page: str, page_no: int = 1, total_pages: int = 0, bounded: bool = False) -> bool:
    """Detect 'ARRANGEMENT OF SECTIONS' style table-of-contents pages.

    TOC pages list one short section heading per line, number-first; body pages
    wrap long prose. Counting hits alone over-matches body pages (which
    reference many sections inline), so require short lines too.

    The number-first pattern is used for this check regardless of the body's
    header style: arrangements are always printed as "12A. Title", while body
    headers may put the title above the number. Counting both patterns at once
    flags rule-PDF body pages as TOC and silently drops content (measured: -28
    chunks on the CGST Rules).
    """
    # An arrangement only ever sits at the front of a statute. Without this
    # bound, schedule pages (long tables whose rows are "1. ...", "2. ...")
    # get classified as TOC and the deduction tables vanish from the corpus.
    if bounded:
        # Gazette two-column documents: only an explicit arrangement/contents
        # heading counts. The short-line heuristic alone flags definition and
        # schedule tables as TOC and drops real body text (measured: -17 pages
        # of section 2 definitions in the 2025 Act).
        explicit = "ARRANGEMENT OF SECTIONS" in page or page.lstrip().startswith("CONTENTS")
        if not explicit:
            return False

    lines = [ln for ln in page.splitlines() if ln.strip()]
    if not lines:
        return False
    hits = sum(1 for ln in lines if SECTION_RE.match(ln))
    long_lines = sum(1 for ln in lines if len(ln.strip()) > 95)
    if "ARRANGEMENT OF SECTIONS" in page or page.lstrip().startswith("CONTENTS"):
        return hits >= 5
    return hits >= 8 and long_lines <= len(lines) * 0.2


def looks_like_title(line: str) -> bool:
    s = line.strip()
    if not TITLE_LINE_RE.match(s):
        return False
    if s.startswith("(") or len(s) < 6:
        return False
    if sum(ch.isdigit() for ch in s) > 4:  # table rows / form fields
        return False
    return True


# --------------------------------------------------------------------------- #
# statute parsing
# --------------------------------------------------------------------------- #

Row = tuple[str | None, str | None, str | None, int, str]


def scan_rows(pages: list[str], header_style: str) -> list[Row]:
    """Turn pages into (section, title, chapter, page, line) rows."""
    rows: list[Row] = []
    cur_sec: str | None = None
    cur_title: str | None = None
    cur_chap: str | None = None
    prev_line = ""

    for page_no, page in enumerate(pages, start=1):
        if is_toc_page(page, page_no, len(pages), bounded=False):
            continue
        for line in page.splitlines():
            stripped = line.strip()
            if not stripped:
                rows.append((cur_sec, cur_title, cur_chap, page_no, ""))
                continue
            if CHAPTER_RE.match(stripped):
                cur_chap = stripped.split()[1] if len(stripped.split()) > 1 else stripped
                rows.append((cur_sec, cur_title, cur_chap, page_no, stripped))
                prev_line = stripped
                continue

            if header_style == "inline":
                m = SECTION_RE.match(line)
                # Guard against numbered lists inside a section (e.g. "(a) 12. ...")
                if m and not stripped.startswith("(") and len(m.group(2).split()) >= 2:
                    cur_sec, cur_title = m.group(1), m.group(2).strip().rstrip(".")
            else:  # "above": the title line arrives before the number line
                m = NUM_HEAD_RE.match(line)
                if m and not stripped.startswith("(") and looks_like_title(prev_line):
                    cur_sec, cur_title = m.group(1), prev_line.strip().rstrip(".")

            rows.append((cur_sec, cur_title, cur_chap, page_no, stripped))
            prev_line = stripped
    return rows


def _section_number(sec: str) -> int:
    """Numeric part of a section key ("80C" -> 80); -1 when it has none."""
    m = re.match(r"^(\d+)", sec)
    return int(m.group(1)) if m else -1


def _sort_key(sec: str) -> tuple[int, str]:
    n = _section_number(sec)
    return (n, sec[len(str(n)):])


def _anchor_starts(flat: list[tuple[int, str]]) -> dict[int, tuple[str, str | None]]:
    """Pass 1: line indexes whose number line carries a first sub-section `(1)`.

    High precision, but blind to sections that have no sub-sections (13, 16, 25).
    Numbers must advance, so a table row inside an earlier section cannot
    restart the sequence.
    """
    starts: dict[int, tuple[str, str | None]] = {}
    last: tuple[int, str] | None = None
    for i, (_page, s) in enumerate(flat):
        m = NUM_HEAD_RE.match(s)
        if not m:
            continue
        has_sub = "(1)" in s[:14] or (i + 1 < len(flat) and flat[i + 1][1].startswith("(1)"))
        if not has_sub:
            continue
        k = _sort_key(m.group(1))
        if last is not None and k <= last:
            continue
        prev = flat[i - 1][1] if i else ""
        starts[i] = (m.group(1), prev.rstrip(".") if looks_like_title(prev) else None)
        last = k
    return starts


def _fill_gaps(flat: list[tuple[int, str]], starts: dict[int, tuple[str, str | None]]) -> None:
    """Pass 2: recover missing section numbers between two anchors, in place.

    Bounded by the neighbouring anchors - an unbounded "previous line looks like
    a title" rule accepts table rows inside section 2 as section 100.
    """
    top = max((_section_number(sec) for sec, _ in starts.values()), default=0)
    known = {_section_number(sec) for sec, _ in starts.values()}
    for want in range(1, top + 1):
        if want in known:
            continue
        lo = max((i for i, (sec, _t) in starts.items() if _section_number(sec) < want), default=-1)
        hi = min((i for i, (sec, _t) in starts.items() if _section_number(sec) > want), default=len(flat))
        for i in range(lo + 1, hi):
            m = NUM_HEAD_RE.match(flat[i][1])
            if not m or _section_number(m.group(1)) != want:
                continue
            prev = flat[i - 1][1] if i else ""
            nxt = flat[i + 1][1] if i + 1 < len(flat) else ""
            if looks_like_title(prev) or nxt.startswith("(1)"):
                starts[i] = (m.group(1), prev.rstrip(".") if looks_like_title(prev) else None)
                known.add(want)
                break


def scan_rows_above(pages: list[str]) -> list[Row]:
    """Parse documents whose section header sits ABOVE the number line.

    Gazette shape (Income-tax Act, 2025 as amended):

        Repeal and savings.
        536.(1) The Income-tax Act, 1961 (43 of 1961) is hereby repealed.

    Two passes (see `_anchor_starts`, `_fill_gaps`): anchors first, then
    gap-fill bounded by the surrounding anchors. Measured on the 2025 Act:
    536 sections -> 509 anchored, 27 unparsed (reported, not hidden).
    """
    flat: list[tuple[int, str]] = []
    for page_no, page in enumerate(pages, start=1):
        if is_toc_page(page, page_no, len(pages), bounded=True):
            continue
        for line in page.splitlines():
            s = line.strip()
            if s:
                flat.append((page_no, s))

    starts = _anchor_starts(flat)
    _fill_gaps(flat, starts)

    rows: list[Row] = []
    cur_sec: str | None = None
    cur_title: str | None = None
    cur_chap: str | None = None
    for i, (page_no, line) in enumerate(flat):
        if i in starts:
            cur_sec, cur_title = starts[i]
        chap = CHAPTER_RE.match(line)
        part = PART_RE.match(line)
        if chap and line.split()[0].upper() == "SCHEDULE":
            # Schedules follow section 536; without this they all inherit
            # "Section 536" and a schedule table cites the repeal clause.
            label = line.split()[1] if len(line.split()) > 1 else ""
            cur_sec = f"SCHEDULE {label}".strip()
            cur_title = f"Schedule {label}".strip()
            cur_chap = cur_sec
        elif chap:
            cur_chap = line.split()[1] if len(line.split()) > 1 else line
        elif part:
            cur_chap = f"{part.group(1)}.--{part.group(2).strip()}"
        rows.append((cur_sec, cur_title, cur_chap, page_no, line))
    return rows


def count_sections(pages: list[str], header_style: str) -> int:
    rows = scan_rows_above(pages) if header_style == "above" else scan_rows(pages, header_style)
    return len({r[0] for r in rows if r[0]})


def detect_header_style(pages: list[str]) -> str:
    """Pick the style that recovers more distinct section numbers."""
    inline = count_sections(pages, "inline")
    above = count_sections(pages, "above")
    style = "inline" if inline >= above else "above"
    print(f"    auto-detected header style: {style} (inline={inline}, above={above})",
          end=" ", flush=True)
    return style


def ingest_statute(path: Path, doc: dict, pdf_mode: str, header_style: str) -> list[Chunk]:
    pages = pdf_to_pages(path, pdf_mode)
    if not pages:
        return []
    rows = scan_rows_above(pages) if header_style == "above" else scan_rows(pages, header_style)
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
                id=f"{doc['doc_id']}:{g['section'] or 'x'}:{i}",
                doc_id=doc["doc_id"], doc_title=doc["title"], doc_type=doc["doc_type"],
                vintage=doc.get("vintage"), applies_to_ay=doc.get("applies_to_ay"),
                section=g["section"], section_title=g["section_title"],
                chapter=g["chapter"], page=g["page"], chunk_index=i,
                text=piece, chars=len(piece),
            ))
    return chunks


def ingest_faqs(path: Path, doc: dict) -> list[Chunk]:
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
                    doc_id=doc["doc_id"], doc_title=doc["title"], doc_type="faq",
                    vintage=doc.get("vintage"), applies_to_ay=doc.get("applies_to_ay"),
                    section=None, section_title=None, chapter=None,
                    page=0, chunk_index=i, text=piece, chars=len(piece),
                ))
    return chunks


# --------------------------------------------------------------------------- #
# manifest
# --------------------------------------------------------------------------- #

def load_manifest() -> list[dict]:
    if not MANIFEST.exists():
        sys.exit(f"manifest missing: {MANIFEST}")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["documents"]


def infer_doc(path: Path) -> dict:
    """Metadata for a PDF the manifest does not know (never a silent skip)."""
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")
    print(f"  ! {path.name} is not in data/manifest.json - ingesting with inferred metadata")
    return {
        "file": path.name, "doc_id": slug, "title": path.stem.replace("_", " ").title(),
        "doc_type": "act", "vintage": None, "applies_to_ay": None,
        "publisher": None, "source_url": None, "license": None, "inferred": True,
    }


def sha256_16(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def discover_docs() -> list[dict]:
    """Manifest documents plus any PDF dropped into data/raw/ that it misses."""
    docs = load_manifest()
    mapped = {d["file"] for d in docs}
    for extra in sorted(RAW.glob("*.pdf")):
        if extra.name not in mapped:
            docs.append(infer_doc(extra))
    return docs


def ingest_document(doc: dict) -> tuple[list[Chunk], dict] | None:
    """Chunks + a stats entry for one document; None when the file is absent."""
    path = RAW / doc["file"]
    if not path.exists():
        print(f"- skip {doc['file']} (missing - see data/README.md)")
        return None

    print(f"+ {doc['file']} ...", end=" ", flush=True)
    if path.suffix.lower() == ".csv":
        produced = ingest_faqs(path, doc)
        entry: dict = {"chunks": len(produced)}
    else:
        pdf_mode = doc.get("pdf_mode", "layout")
        header_style = doc.get("header_style", "auto")
        if header_style == "auto":
            pages = pdf_to_pages(path, pdf_mode)
            header_style = detect_header_style(pages) if pages else "inline"
        produced = ingest_statute(path, doc, pdf_mode, header_style)
        declared = doc.get("declared_sections")
        parsed_all = entry_sections(produced)
        # schedules are their own keys but are NOT numbered sections, so they
        # must not count towards the declared-section reconciliation
        parsed_numbered = len({c.section for c in produced
                               if c.section and c.section[:1].isdigit()})
        entry = {
            "chunks": len(produced), "pdf_mode": pdf_mode,
            "header_style": header_style,
            "sections": parsed_all, "sections_numbered": parsed_numbered,
            # only set when the manifest declares the document's own count
            "sections_unparsed": (declared - parsed_numbered) if declared else None,
        }
    print(f"{len(produced)} chunks")
    return produced, entry


def entry_sections(chunks: list[Chunk]) -> int:
    """Distinct section keys, including SCHEDULE I..XVI."""
    return len({c.section for c in chunks if c.section})


def write_outputs(all_chunks: list[Chunk], docs: list[dict], report: dict[str, dict]) -> None:
    with (OUT / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for c in all_chunks:
            fh.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")

    by_doc: dict[str, int] = {}
    for c in all_chunks:
        by_doc[c.doc_id] = by_doc.get(c.doc_id, 0) + 1

    stats = {
        "pdftotext_version": pdftotext_version(),
        "documents": {
            d["doc_id"]: {
                "file": d["file"], "title": d["title"], "type": d["doc_type"],
                "vintage": d.get("vintage"), "applies_to_ay": d.get("applies_to_ay"),
                "sha256_16": sha256_16(RAW / d["file"]) if (RAW / d["file"]).exists() else None,
                **report.get(d["doc_id"], {}),
            }
            for d in docs if report.get(d["doc_id"])
        },
        "chunks": len(all_chunks),
        "chunks_by_doc": by_doc,
        "documents_with_sections": sorted({c.doc_id for c in all_chunks if c.section}),
        "distinct_sections": len({(c.doc_id, c.section) for c in all_chunks if c.section}),
        "total_chars": sum(c.chars for c in all_chunks),
        "avg_chars": round(sum(c.chars for c in all_chunks) / max(len(all_chunks), 1)),
        "max_chars": max((c.chars for c in all_chunks), default=0),
    }
    (OUT / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(json.dumps({k: stats[k] for k in
                      ("chunks", "chunks_by_doc", "distinct_sections", "total_chars")}, indent=2))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    docs = discover_docs()
    all_chunks: list[Chunk] = []
    report: dict[str, dict] = {}

    for doc in docs:
        result = ingest_document(doc)
        if result is None:
            continue
        produced, entry = result
        report[doc["doc_id"]] = entry
        all_chunks.extend(produced)

    write_outputs(all_chunks, docs, report)


if __name__ == "__main__":
    main()
