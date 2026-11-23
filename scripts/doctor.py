#!/usr/bin/env python3
"""
Environment + corpus integrity check. Run this first on a new machine.

    python scripts/doctor.py

Checks, in order:

1. Python >= 3.11 and that ingestion's stdlib-only claim still holds.
2. `pdftotext` (poppler) is on PATH - the only external binary we need.
3. Every document in `data/manifest.json` exists in `data/raw/` and matches the
   SHA-256 prefix recorded in `data/sources.json`.
4. `data/processed/chunks.jsonl` exists and per-document chunk counts equal the
   pins recorded for the pdftotext build that produced it (see PIN_SETS).
5. Manifest/sources agreement: no document is described in one place only.

Exit code 0 = a corpus you can cite from. Non-zero prints exactly what to fix,
and the fix is always one of: `python scripts/fetch_corpus.py`,
`python scripts/ingest.py`, or installing poppler.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
MANIFEST = ROOT / "data" / "manifest.json"
SOURCES = ROOT / "data" / "sources.json"

# Pinned so a "harmless" parser tweak cannot silently shrink the corpus.
# Two real regressions were caught this way: -28 chunks (TOC heuristic) and
# -23 sections (a header printed "9.(1)" with no space).
#
# Pins are per pdftotext build: poppler versions lay the same PDF out
# differently (24.02 lifts footnote superscripts onto their own line, which once
# cost 279 sections of the 1961 Act). A new set is added only after the spot
# checks in AGENTS.md show that build's output is complete - never to make a
# drifted run pass, and an existing set is never edited to match a new run.
FAQ_CHUNKS = 1317  # CSV, parsed without poppler, so identical in every set
PIN_SETS: tuple[dict, ...] = (
    {
        "pdftotext": None,
        "label": "reference build (author's Windows machine, 2026-11-21, version not recorded)",
        "chunks": {"it-act-2025": 1779, "it-rules-2026": 2675, "it-act-1961": 3868,
                   "cgst-act-2017": 578, "cgst-rules-2017": 863, "faq-cbdt": FAQ_CHUNKS},
    },
    {
        "pdftotext": "24.02.0",
        "label": "poppler-utils 24.02.0 (Ubuntu 24.04), 2026-11-23",
        "chunks": {"it-act-2025": 1781, "it-rules-2026": 2680, "it-act-1961": 3845,
                   "cgst-act-2017": 579, "cgst-rules-2017": 889, "faq-cbdt": FAQ_CHUNKS},
    },
    {
        "pdftotext": "26.11.0",
        "label": "poppler 26.11.0 (Homebrew, macOS arm64), 2026-11-22",
        # Measured after SECTION_RE accepted three-letter suffixes (44ADA, 80CCD):
        # the 1961 Act gains section keys the two-letter pattern merged away.
        "chunks": {"it-act-2025": 1762, "it-rules-2026": 2670, "it-act-1961": 3852,
                   "cgst-act-2017": 579, "cgst-rules-2017": 889, "faq-cbdt": FAQ_CHUNKS},
    },
)


@dataclass
class Findings:
    ok: list[str] = field(default_factory=list)
    warn: list[str] = field(default_factory=list)
    fail: list[str] = field(default_factory=list)

    def check(self, cond: bool, good: str, bad: str) -> None:
        (self.ok if cond else self.fail).append(good if cond else bad)


def sha256_16(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def pdftotext_version() -> str | None:
    """Version of the pdftotext on PATH (it prints to stderr), or None."""
    try:
        res = subprocess.run(
            ["pdftotext", "-v"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return None
    m = re.search(r"version\s+(\S+)", res.stderr + res.stdout)
    return m.group(1) if m else None


def load_corpus() -> tuple[list[dict], dict[str, dict]]:
    docs = json.loads(MANIFEST.read_text(encoding="utf-8"))["documents"]
    sources = ({d["doc_id"]: d for d in
                json.loads(SOURCES.read_text(encoding="utf-8"))["documents"]}
               if SOURCES.exists() else {})
    return docs, sources


def check_documents(docs: list[dict], sources: dict[str, dict], f: Findings) -> None:
    """Presence + hash for every document; manual-acquire files are warnings."""
    missing_docs, missing_manual, hash_bad = [], [], []
    for doc in docs:
        path = RAW / doc["file"]
        if not path.exists():
            (missing_manual if doc.get("acquire") == "manual" else missing_docs).append(doc["file"])
            continue
        want = doc.get("sha256_16") or sources.get(doc["doc_id"], {}).get("sha256_16")
        have = sha256_16(path) if want else None
        if want and have != want:
            hash_bad.append(f"{doc['file']} (have {have}, want {want})")

    if missing_docs:
        f.fail.append(f"{len(missing_docs)} document(s) missing from data/raw: "
                      f"{', '.join(missing_docs)} -> run: python scripts/fetch_corpus.py")
    if hash_bad:
        f.fail.append(f"hash mismatch: {'; '.join(hash_bad)} -> re-fetch that file")
    if missing_manual:
        f.warn.append("eval-only document(s) not present: " + ", ".join(missing_manual)
                      + " -> manual download, see data/manifest.json acquire_hint")
    if not missing_docs and not hash_bad:
        f.ok.append(f"all {len(docs) - len(missing_manual)} available documents present and hash-verified")

    unrecorded = [d["doc_id"] for d in docs
                  if not (d.get("sha256_16") or sources.get(d["doc_id"], {}).get("sha256_16"))]
    if unrecorded:
        f.warn.append(f"no recorded hash for {', '.join(unrecorded)} - cannot verify re-downloads")

    only_in_sources = set(sources) - {d["doc_id"] for d in docs}
    if only_in_sources:
        f.warn.append(f"in sources.json but not in the manifest: {', '.join(sorted(only_in_sources))}")


def _drift(counts: dict[str, int], pins: dict[str, int]) -> dict[str, tuple[int, int]]:
    """Present documents whose count differs from the pin: {doc: (have, want)}."""
    return {k: (counts[k], v) for k, v in pins.items() if k in counts and counts[k] != v}


def pin_findings(counts: dict[str, int], built_with: str | None) -> Findings:
    """Compare per-document chunk counts with the pins for the build that made them.

    A pure function of its inputs so the gate itself is unit-tested.
    """
    f = Findings()
    if not counts:
        f.fail.append("stats.json has no chunks_by_doc -> re-run python scripts/ingest.py")
        return f

    pin_set = next((p for p in PIN_SETS if p["pdftotext"] and p["pdftotext"] == built_with), None)
    if pin_set:
        drift = _drift(counts, pin_set["chunks"])
        if drift:
            f.fail.append(f"chunk counts drifted for pdftotext {built_with} (doc: have vs expected): "
                          + ", ".join(f"{k}: {h} vs {e}" for k, (h, e) in drift.items())
                          + " -> inspect the parser, do NOT just update the pin")
            return f
    else:
        pin_set = next((p for p in PIN_SETS
                        if not _drift(counts, p["chunks"]) and set(counts) & set(p["chunks"])), None)
        if pin_set is None:
            known = ", ".join(p["label"] for p in PIN_SETS)
            f.fail.append(f"no pin set for pdftotext {built_with or '(not recorded - re-run ingest.py)'} "
                          f"and the counts match none of: {known} -> spot-check this build's "
                          f"extraction (AGENTS.md), then ADD a pin set; never edit an existing one")
            return f
        f.warn.append(f"pdftotext {built_with or '(not recorded)'} has no pin set of its own, but its "
                      f"counts match the {pin_set['label']} -> record the version in PIN_SETS")

    present = [k for k in pin_set["chunks"] if k in counts]
    f.ok.append(f"chunk counts match the pins ({pin_set['label']}) for "
                f"{len(present)}/{len(pin_set['chunks'])} document(s), {sum(counts.values())} chunks")
    expected_total = sum(pin_set["chunks"].values())
    if sum(counts.values()) != expected_total:
        f.warn.append(f"total {sum(counts.values())} != pinned {expected_total} chunks: an eval-only "
                      f"document is probably missing, so eval numbers here are NOT comparable "
                      f"with a full-corpus run (quote corpus_hash)")
    return f


def check_processed(f: Findings) -> None:
    """Chunk file, pinned per-document counts, and the corpus hash."""
    chunks_file = PROCESSED / "chunks.jsonl"
    if not chunks_file.exists():
        f.fail.append("data/processed/chunks.jsonl missing -> run: python scripts/ingest.py")
        return

    stats_path = PROCESSED / "stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    built_with = stats.get("pdftotext_version")
    on_path = pdftotext_version()
    if built_with and on_path and built_with != on_path:
        f.warn.append(f"corpus was built with pdftotext {built_with} but {on_path} is on PATH "
                      f"-> re-run python scripts/ingest.py before trusting new chunks")

    result = pin_findings(stats.get("chunks_by_doc", {}), built_with)
    f.ok += result.ok
    f.warn += result.warn
    f.fail += result.fail

    h = hashlib.sha256()
    with chunks_file.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    print(f"\ncorpus_hash(sha256:12) = {h.hexdigest()[:12]}  "
          f"(pdftotext {built_with or 'unrecorded'}; quote both in every eval report)")


def main() -> int:
    print("AskDocs doctor\n" + "=" * 60)
    f = Findings()

    # 1. interpreter
    v = sys.version_info
    f.check(v >= (3, 11), f"python {v.major}.{v.minor}.{v.micro}",
            f"python {v.major}.{v.minor} is too old - use 3.11+")

    # 2. poppler
    pdftotext = shutil.which("pdftotext")
    f.check(bool(pdftotext), f"pdftotext {pdftotext_version()} found at {pdftotext}",
            "pdftotext missing - install poppler "
            "(Windows: winget install oschwartz10612.Poppler | Debian: apt install poppler-utils)")

    # 3. documents
    if not MANIFEST.exists():
        f.fail.append(f"manifest missing: {MANIFEST}")
        return report(f)
    docs, sources = load_corpus()
    check_documents(docs, sources, f)

    # 4. processed corpus
    check_processed(f)

    # 5. vintage metadata, the thing that keeps answers honest
    no_vintage = [d["doc_id"] for d in docs if not d.get("vintage")]
    f.check(not no_vintage, "every document declares a vintage",
            f"documents with no vintage: {', '.join(no_vintage)}")

    return report(f)


def report(f: Findings) -> int:
    print()
    for line in f.ok:
        print(f"  PASS  {line}")
    for line in f.warn:
        print(f"  WARN  {line}")
    for line in f.fail:
        print(f"  FAIL  {line}")
    print("=" * 60)
    if f.fail:
        print(f"{len(f.fail)} blocking problem(s). Citations are not trustworthy until fixed.")
        return 1
    print("READY - corpus verified." + (f" ({len(f.warn)} warning(s))" if f.warn else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
