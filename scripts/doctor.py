#!/usr/bin/env python3
"""
Environment + corpus integrity check. Run this first on a new machine.

    python scripts/doctor.py

Checks, in order:

1. Python >= 3.11 and that ingestion's stdlib-only claim still holds.
2. `pdftotext` (poppler) is on PATH - the only external binary we need.
3. Every document in `data/manifest.json` exists in `data/raw/` and matches the
   SHA-256 prefix recorded in `data/sources.json`.
4. `data/processed/chunks.jsonl` exists, is deterministic-sized, and per-document
   chunk counts still equal the pinned expectations.
5. Manifest/sources agreement: no document is described in one place only.

Exit code 0 = a corpus you can cite from. Non-zero prints exactly what to fix,
and the fix is always one of: `python scripts/fetch_corpus.py`,
`python scripts/ingest.py`, or installing poppler.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
MANIFEST = ROOT / "data" / "manifest.json"
SOURCES = ROOT / "data" / "sources.json"

# Pinned so a "harmless" parser tweak cannot silently shrink the corpus.
# Two real regressions were caught this way: -28 chunks (TOC heuristic) and
# -23 sections (a header printed "9.(1)" with no space).
EXPECTED_CHUNKS = {
    "it-act-2025": 1779,
    "it-rules-2026": 2675,
    "it-act-1961": 3868,
    "cgst-act-2017": 578,
    "cgst-rules-2017": 863,
    "faq-cbdt": 1317,
}
TOTAL_CHUNKS = 11080

ok, fail, warn = [], [], []


def check(cond: bool, good: str, bad: str) -> None:
    (ok if cond else fail).append(good if cond else bad)


def sha256_16(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def load_corpus() -> tuple[list[dict], dict[str, dict]]:
    docs = json.loads(MANIFEST.read_text(encoding="utf-8"))["documents"]
    sources = ({d["doc_id"]: d for d in
                json.loads(SOURCES.read_text(encoding="utf-8"))["documents"]}
               if SOURCES.exists() else {})
    return docs, sources


def check_documents(docs: list[dict], sources: dict[str, dict]) -> None:
    """Presence + hash for every document; manual-acquire files are warnings."""
    if not MANIFEST.exists():
        fail.append(f"manifest missing: {MANIFEST}")
        return report()
    docs = json.loads(MANIFEST.read_text(encoding="utf-8"))["documents"]
    sources = ({d["doc_id"]: d for d in
                json.loads(SOURCES.read_text(encoding="utf-8"))["documents"]}
               if SOURCES.exists() else {})

    missing_docs, missing_manual, hash_bad = [], [], []
    for doc in docs:
        path = RAW / doc["file"]
        if not path.exists():
            (missing_manual if doc.get("acquire") == "manual" else missing_docs).append(doc["file"])
            continue
        want = doc.get("sha256_16") or sources.get(doc["doc_id"], {}).get("sha256_16")
        if want and sha256_16(path) != want:
            hash_bad.append(f"{doc['file']} (have {sha256_16(path)}, want {want})")

    if missing_docs:
        fail.append(f"{len(missing_docs)} document(s) missing from data/raw: "
                    f"{', '.join(missing_docs)} -> run: python scripts/fetch_corpus.py")
    if hash_bad:
        fail.append(f"hash mismatch: {'; '.join(hash_bad)} -> re-fetch that file")
    if missing_manual:
        warn.append("eval-only document(s) not present: " + ", ".join(missing_manual)
                    + " -> manual download, see data/manifest.json acquire_hint")
    if not missing_docs and not hash_bad:
        ok.append(f"all {len(docs) - len(missing_manual)} available documents present and hash-verified")

    unrecorded = [d["doc_id"] for d in docs
                  if not (d.get("sha256_16") or sources.get(d["doc_id"], {}).get("sha256_16"))]
    if unrecorded:
        warn.append(f"no recorded hash for {', '.join(unrecorded)} - cannot verify re-downloads")

    only_in_sources = set(sources) - {d["doc_id"] for d in docs}
    if only_in_sources:
        warn.append(f"in sources.json but not in the manifest: {', '.join(sorted(only_in_sources))}")


def check_processed() -> None:
    """Chunk file, pinned per-document counts, and the corpus hash."""
    chunks_file = PROCESSED / "chunks.jsonl"
    if not chunks_file.exists():
        fail.append("data/processed/chunks.jsonl missing -> run: python scripts/ingest.py")
        return

    stats_path = PROCESSED / "stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    counts = stats.get("chunks_by_doc", {})
    if not counts:
        fail.append("stats.json missing or unreadable -> re-run python scripts/ingest.py")
    else:
        drift = {k: (counts.get(k), v) for k, v in EXPECTED_CHUNKS.items()
                 if counts.get(k) is not None and counts.get(k) != v}
        if drift:
            fail.append("chunk counts drifted (doc: have vs expected): "
                        + ", ".join(f"{k}: {h} vs {e}" for k, (h, e) in drift.items())
                        + " -> inspect the parser, do NOT just update the pin")
        else:
            ok.append(f"chunk counts match the pins ({sum(counts.values())} chunks)")
        if stats.get("chunks") != TOTAL_CHUNKS:
            warn.append(f"total chunks {stats.get('chunks')} != pinned {TOTAL_CHUNKS}")

    h = hashlib.sha256()
    with chunks_file.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    print(f"\ncorpus_hash(sha256:12) = {h.hexdigest()[:12]}  "
          f"(quote this in every eval report)")


def main() -> int:
    print("AskDocs doctor\n" + "=" * 60)

    # 1. interpreter
    v = sys.version_info
    check(v >= (3, 11), f"python {v.major}.{v.minor}.{v.micro}",
          f"python {v.major}.{v.minor} is too old - use 3.11+")

    # 2. poppler
    pdftotext = shutil.which("pdftotext")
    check(bool(pdftotext), f"pdftotext found at {pdftotext}",
          "pdftotext missing - install poppler "
          "(Windows: winget install oschwartz10612.Poppler | Debian: apt install poppler-utils)")

    # 3. documents
    if not MANIFEST.exists():
        fail.append(f"manifest missing: {MANIFEST}")
        return report()
    docs, sources = load_corpus()
    check_documents(docs, sources)

    # 4. processed corpus
    check_processed()

    # 5. vintage metadata, the thing that keeps answers honest
    no_vintage = [d["doc_id"] for d in docs if not d.get("vintage")]
    check(not no_vintage, "every document declares a vintage",
          f"documents with no vintage: {', '.join(no_vintage)}")

    return report()


def report() -> int:
    print()
    for line in ok:
        print(f"  PASS  {line}")
    for line in warn:
        print(f"  WARN  {line}")
    for line in fail:
        print(f"  FAIL  {line}")
    print("=" * 60)
    if fail:
        print(f"{len(fail)} blocking problem(s). Citations are not trustworthy until fixed.")
        return 1
    print("READY - corpus verified." + (f" ({len(warn)} warning(s))" if warn else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
