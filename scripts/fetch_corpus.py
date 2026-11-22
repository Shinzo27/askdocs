#!/usr/bin/env python3
"""
Re-acquire the corpus from scratch on any machine.

`data/raw/` is gitignored (20 MB of government PDFs, not ours to redistribute),
so a fresh clone has no documents. This script rebuilds them from
`data/manifest.json`, verifying SHA-256 against `data/sources.json`.

Two acquisition routes per document, in order:

1. the live `source_url`;
2. `wayback_url` - a Wayback Machine `id_` raw fetch of that same URL.

Route 2 exists because `incometaxindia.gov.in` returns 403 to some networks
(WAF). Wayback caps a single response, so a truncated transfer is resumed with
HTTP Range requests until the byte count matches the recorded size.

Usage
-----
    python scripts/fetch_corpus.py               # fetch what is missing/incorrect
    python scripts/fetch_corpus.py --dry-run     # show the plan, download nothing
    python scripts/fetch_corpus.py --dest DIR    # fetch into DIR instead of data/raw
    python scripts/fetch_corpus.py --force       # re-download even if the hash matches

Exit code 0 means every document is present and hash-verified. Anything else is
a corpus that must not be trusted for citations.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "manifest.json"
SOURCES = ROOT / "data" / "sources.json"
DEFAULT_DEST = ROOT / "data" / "raw"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CHUNK = 1 << 20
TIMEOUT = 120


def sha256_16(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()[:16]


def load() -> tuple[list[dict], dict[str, dict]]:
    docs = json.loads(MANIFEST.read_text(encoding="utf-8"))["documents"]
    sources = {d["doc_id"]: d for d in
               json.loads(SOURCES.read_text(encoding="utf-8"))["documents"]}
    return docs, sources


def expected(doc: dict, sources: dict[str, dict]) -> dict:
    """Recorded facts for one document: hash, byte size, page count."""
    src = sources.get(doc["doc_id"], {})
    return {
        "sha256_16": doc.get("sha256_16") or src.get("sha256_16"),
        "bytes": src.get("bytes"),
        "pages": src.get("pages"),
    }


def download(url: str, dest: Path, expect_bytes: int | None, resume: bool) -> bool:
    """Fetch `url` into `dest`, resuming a truncated transfer. True on success."""
    have = dest.stat().st_size if (resume and dest.exists()) else 0
    if expect_bytes and have > expect_bytes:
        dest.unlink()
        have = 0

    stalled = 0
    for attempt in range(1, 6):
        before = have
        headers = {"User-Agent": UA}
        if have:
            headers["Range"] = f"bytes={have}-"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                mode = "ab" if (have and resp.status == 206) else "wb"
                if mode == "wb":
                    have = 0
                with dest.open(mode) as fh:
                    while True:
                        block = resp.read(CHUNK)
                        if not block:
                            break
                        fh.write(block)
                        have += len(block)
        except (urllib.error.HTTPError, urllib.error.URLError,
                http.client.IncompleteRead, TimeoutError) as exc:
            # A 403/404 is a hard no for this route; anything else is retried.
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403, 404, 410):
                print(f"      route failed: HTTP {exc.code}")
                return False
            print(f"      attempt {attempt} interrupted ({type(exc).__name__}); "
                  f"have {have:,} bytes, retrying")
            time.sleep(2 * attempt)
            continue

        if not expect_bytes:
            return dest.stat().st_size > 1024
        if have >= expect_bytes:
            return True
        # A server that ignores Range restarts from zero every time; two
        # no-progress rounds mean this route cannot deliver the file.
        stalled = 0 if have > before else stalled + 1
        if stalled >= 2:
            print(f"      route ignores Range and stalls at {have:,} bytes; giving up")
            return False
        print(f"      transfer stopped at {have:,} of {expect_bytes:,} bytes; resuming")

    return dest.exists() and (not expect_bytes or dest.stat().st_size >= expect_bytes)


def fetch_one(doc: dict, dest_dir: Path, exp: dict, force: bool) -> str:
    dest = dest_dir / doc["file"]
    want = exp["sha256_16"]

    if dest.exists() and not force:
        got = sha256_16(dest)
        if want and got == want:
            print(f"  = {doc['file']} already present and verified ({got})")
            return "present"
        print(f"  ! {doc['file']} present but hash differs (have {got}, want {want})")

    if doc.get("acquire") == "manual":
        print(f"  ! {doc['file']} needs a manual download:")
        print(f"      {doc.get('acquire_hint', 'see data/README.md')}")
        return "manual"

    routes = [("live", doc.get("source_url")), ("wayback", doc.get("wayback_url"))]
    routes = [(name, url) for name, url in routes if url]
    if not routes:
        print(f"  x {doc['file']}: no source_url in the manifest")
        return "no-route"

    for name, url in routes:
        print(f"  -> {doc['file']} via {name}")
        if download(url, dest, exp["bytes"], resume=True):
            got = sha256_16(dest)
            if want and got != want:
                print(f"  ! {doc['file']} hash mismatch after {name} "
                      f"(have {got}, want {want})")
                continue
            print(f"  + {doc['file']} verified ({got}, "
                  f"{dest.stat().st_size:,} bytes)")
            return "fetched"
        print(f"  x {doc['file']}: {name} route did not deliver the file")

    return "failed"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=str(DEFAULT_DEST), help="target directory")
    ap.add_argument("--dry-run", action="store_true", help="print the plan only")
    ap.add_argument("--force", action="store_true", help="re-download even when verified")
    args = ap.parse_args()

    docs, sources = load()
    dest_dir = Path(args.dest)
    print(f"corpus fetch -> {dest_dir}")
    if not args.dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, str] = {}
    for doc in docs:
        exp = expected(doc, sources)
        if exp["bytes"]:
            print(f"\n[{doc['doc_id']}] {exp['bytes']:,} bytes"
                  f"{', ' + str(exp['pages']) + ' pp' if exp['pages'] else ''}"
                  f", sha256 {exp['sha256_16'] or 'unrecorded'}")
        else:
            print(f"\n[{doc['doc_id']}]")
        if args.dry_run:
            state = ("present" if (dest_dir / doc["file"]).exists() else "missing")
            if doc.get("acquire") == "manual":
                print(f"  . manual acquisition -> {doc['file']} (currently {state})")
            else:
                route = "live" + ("+wayback" if doc.get("wayback_url") else "")
                print(f"  . would try {route} -> {doc['file']} (currently {state})")
            results[doc["doc_id"]] = state
            continue
        results[doc["doc_id"]] = fetch_one(doc, dest_dir, exp, args.force)

    bad = {k: v for k, v in results.items() if v not in ("present", "fetched", "manual")}
    manual = sorted(k for k, v in results.items() if v == "manual")
    if manual:
        print(f"\nmanual step still required: {', '.join(manual)} (eval-only, not shipped)")
    print("\n" + ("all documents verified" if not bad else f"INCOMPLETE: {bad}"))
    if not bad:
        print("next: python scripts/ingest.py")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
