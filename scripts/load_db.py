#!/usr/bin/env python3
"""Stream the corpus into Postgres: documents, chunks + vectors, corpus metadata.

Reads `data/processed/chunks.jsonl` and `data/processed/embeddings.npy` (row
aligned), writes `documents` and `chunks` with a COPY, then records the
`corpus_hash` and extractor in `corpus_meta` so the API and every eval report can
quote the corpus they actually ran on.

    python scripts/load_db.py             # load (truncates chunks first)
    python scripts/load_db.py --verify    # compare DB row count with the file
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
CHUNKS = PROCESSED / "chunks.jsonl"
VECTORS = PROCESSED / "embeddings.npy"
STATS = PROCESSED / "stats.json"
MANIFEST = ROOT / "data" / "manifest.json"
EMBED_MANIFEST = PROCESSED / "embedding_manifest.json"


def load_env() -> None:
    """Read the repo-level `.env` into os.environ (the scripts run outside the API)."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def dsn() -> str:
    load_env()
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set - copy .env.example to .env and fill it in")
    # psycopg wants a libpq URL, not SQLAlchemy's asyncpg dialect prefix.
    return url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


def corpus_hash() -> str:
    h = hashlib.sha256()
    with CHUNKS.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_rows() -> tuple[list[dict], np.ndarray, dict]:
    if not CHUNKS.exists():
        sys.exit(f"{CHUNKS} missing - run: python scripts/ingest.py")
    if not VECTORS.exists():
        sys.exit(f"{VECTORS} missing - run: python scripts/embed.py")
    rows = [json.loads(line) for line in CHUNKS.read_text(encoding="utf-8").splitlines() if line]
    vectors = np.load(VECTORS)
    if vectors.shape[0] != len(rows):
        sys.exit(f"row mismatch: {vectors.shape[0]} vectors vs {len(rows)} chunks - re-run embed.py")
    stats = json.loads(STATS.read_text(encoding="utf-8")) if STATS.exists() else {}
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))["documents"]
    return rows, vectors, {"stats": stats, "manifest": {d["doc_id"]: d for d in manifest}}


def document_rows(meta: dict) -> list[tuple]:
    """One row per document, with the honest `sections_unparsed` figure."""
    sources = {}
    if (PROCESSED.parent / "sources.json").exists():
        sources = {
            d["doc_id"]: d
            for d in json.loads((PROCESSED.parent / "sources.json").read_text(encoding="utf-8"))[
                "documents"
            ]
        }
    out = []
    for doc_id, entry in meta["stats"].get("documents", {}).items():
        if entry.get("type") == "faq":
            continue  # eval-only: licensed for neither redistribution nor citation
        declared = meta["manifest"].get(doc_id, {})
        out.append(
            (
                doc_id,
                entry["title"],
                entry["type"],
                declared.get("publisher"),
                entry.get("vintage"),
                entry.get("applies_to_ay"),
                declared.get("source_url"),
                entry.get("sha256_16") or "",
                sources.get(doc_id, {}).get("pages"),
                entry.get("sections_unparsed"),
            )
        )
    return out


def vector_literal(vector) -> str:
    """pgvector's text format is `[a,b,c]`; psycopg would send a Python list as `{a,b,c}`."""
    return "[" + ",".join(f"{float(v):.6f}" for v in vector) + "]"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true", help="compare counts, load nothing")
    args = ap.parse_args()

    import psycopg

    rows, vectors, meta = load_rows()
    chash = corpus_hash()

    # The CBDT FAQ mirror declares no licence and is documented as eval-only
    # ("never shipped, never redistributed" - data/README.md). Indexing it broke the
    # product's premise as well as its licensing: FAQ text is shaped like a question,
    # so it out-ranked every statute chunk for natural questions while carrying no
    # section to cite. Measured cost of indexing it: recall@10 0.80 -> 0.68 on the
    # Week 1 subset, with 4 of 5 misses topped by `faq` chunks.
    shipped = {doc_id for doc_id, entry in meta["stats"].get("documents", {}).items()
               if entry.get("type") != "faq"}
    keep = [i for i, row in enumerate(rows) if row["doc_id"] in shipped]
    if len(keep) != len(rows):
        print(f"indexing {len(keep)} of {len(rows)} chunks "
              f"(excluded {len(rows) - len(keep)} eval-only FAQ chunks)")
    rows = [rows[i] for i in keep]
    vectors = vectors[keep]

    with psycopg.connect(dsn(), autocommit=False) as conn, conn.cursor() as cur:
        if args.verify:
            cur.execute("SELECT count(*) FROM chunks")
            in_db = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM documents")
            docs = cur.fetchone()[0]
            print(f"db: {in_db} chunks / {docs} documents; file: {len(rows)} chunks")
            ok = in_db == len(rows)
            print("OK" if ok else "DRIFT - re-run: python scripts/load_db.py")
            return 0 if ok else 1

        started = time.perf_counter()
        cur.execute("TRUNCATE chunks, documents CASCADE")

        with cur.copy(
            "COPY documents (doc_id, title, doc_type, publisher, vintage, applies_to_ay,"
            " source_url, sha256, pages, sections_unparsed) FROM STDIN"
        ) as copy:
            for row in document_rows(meta):
                copy.write_row(row)

        with cur.copy(
            "COPY chunks (id, doc_id, section, section_title, chapter, page, chunk_index,"
            " text, chars, omitted, embedding) FROM STDIN"
        ) as copy:
            for row, vector in zip(rows, vectors, strict=True):
                copy.write_row(
                    (
                        row["id"],
                        row["doc_id"],
                        row["section"],
                        row["section_title"],
                        row["chapter"],
                        row["page"],
                        row["chunk_index"],
                        row["text"],
                        row["chars"],
                        bool(row.get("omitted", False)),
                        vector_literal(vector),
                    )
                )

        extractor = meta["stats"].get("pdftotext_version")
        for key, value in (
            ("corpus_hash", chash),
            ("extractor", extractor or ""),
            ("chunks", str(len(rows))),
            ("embedding_model", (json.loads(EMBED_MANIFEST.read_text())
                                 ["model"] if EMBED_MANIFEST.exists() else "")),
        ):
            cur.execute(
                "INSERT INTO corpus_meta (key, value) VALUES (%s, %s)"
                " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,"
                " updated_at = now()",
                (key, value),
            )
        cur.execute(
            "TRUNCATE lexeme_stats;"
            " INSERT INTO lexeme_stats (lexeme, ndoc, nentry)"
            " SELECT word, ndoc, nentry FROM ts_stat('SELECT tsv FROM chunks');"
        )
        cur.execute("ANALYZE chunks")
        cur.execute("ANALYZE lexeme_stats")
        conn.commit()

    elapsed = time.perf_counter() - started
    print(f"loaded {len(rows)} chunks in {elapsed:.1f}s")
    print(f"corpus_hash {chash[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
