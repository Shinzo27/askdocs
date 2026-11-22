#!/usr/bin/env python3
"""Embed the corpus once, idempotently, and record what produced the vectors.

Writes `data/processed/embeddings.npy` (float32, row-aligned with chunks.jsonl)
plus `data/processed/embedding_manifest.json`. The manifest is the guard against
silently mixing two models: it records model, dimension, chunk count and the
`corpus_hash` of the chunk file the vectors were built from.

Idempotent by content: a re-run whose model, dimension and corpus hash all match
does nothing. `--force` re-encodes.

    python scripts/embed.py            # encode if needed
    python scripts/embed.py --force    # re-encode regardless
    python scripts/embed.py --check    # verify only; exit 1 when stale
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
CHUNKS = PROCESSED / "chunks.jsonl"
VECTORS = PROCESSED / "embeddings.npy"
MANIFEST = PROCESSED / "embedding_manifest.json"

MODEL = "BAAI/bge-small-en-v1.5"
DIM = 384


def corpus_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_chunks() -> list[dict]:
    with CHUNKS.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def current_manifest(chunks: list[dict]) -> dict:
    return {
        "model": MODEL,
        "dimension": DIM,
        "chunks": len(chunks),
        "corpus_hash": corpus_hash(CHUNKS),
        "normalised": True,
        "query_prefix": "Represent this sentence for searching relevant passages: ",
        # Vectors are a function of the text, not of chunk ids: a re-ingest that
        # only renumbers ids must not force a 45-minute re-encode.
        "texts_hash": hashlib.sha256(
            "\n".join(c["text"] for c in chunks).encode("utf-8")
        ).hexdigest()[:16],
    }


def is_current(want: dict) -> bool:
    if not (VECTORS.exists() and MANIFEST.exists()):
        return False
    have = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return all(
        have.get(k) == want[k]
        for k in ("model", "dimension", "chunks", "corpus_hash", "texts_hash")
    )


def adopt_vectors(chunks: list[dict], want: dict) -> int:
    """Re-point an existing vector file at a re-ingested corpus after checking it.

    Ids change when the parser changes how sections resume; the vectors do not.
    Rather than trust that, encode a spread of rows from scratch and require an
    exact match (cosine ≥ 0.9999) before rewriting the manifest.
    """
    if not VECTORS.exists():
        sys.exit("no embeddings to adopt - run: python scripts/embed.py")
    vectors = np.load(VECTORS)
    if vectors.shape != (len(chunks), DIM):
        sys.exit(f"shape {vectors.shape} != ({len(chunks)}, {DIM}) - re-encode instead")

    sample = np.linspace(0, len(chunks) - 1, 8, dtype=int)
    fresh = encode([chunks[i] for i in sample], batch_size=8)
    cosines = [
        float(np.dot(vectors[i], fresh[j]) / (np.linalg.norm(vectors[i]) * np.linalg.norm(fresh[j])))
        for j, i in enumerate(sample)
    ]
    worst = min(cosines)
    if worst < 0.9999:
        sys.exit(f"sample mismatch (min cosine {worst:.4f}) - the text moved; "
                 f"re-run: python scripts/embed.py --force")

    MANIFEST.write_text(json.dumps(want, indent=2) + "\n", encoding="utf-8")
    print(f"adopted existing vectors: {len(chunks)} rows, sample cosine min {worst:.6f}")
    print(f"manifest now quotes corpus_hash {want['corpus_hash'][:12]}")
    return 0


def encode(chunks: list[dict], batch_size: int = 64) -> np.ndarray:
    """Encode passages in batches.

    Batch 64 measured ~35 texts/s on an 8-core M-series CPU; the same box drops to
    ~7 texts/s when another process (an npm install, a second encoder) competes for
    cores, and torch thread oversubscription on this build produced a 900 s batch.
    So: one encoder at a time, default thread count, no tuning beyond batch size.
    """
    import torch  # local import: embedding is the only torch consumer here
    from sentence_transformers import SentenceTransformer

    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    print(f"loading {MODEL} ...", end=" ", flush=True)
    model = SentenceTransformer(MODEL, device="cpu")
    print("ok")
    texts = [c["text"] for c in chunks]
    started = time.perf_counter()
    out = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    elapsed = time.perf_counter() - started
    print(f"encoded {len(texts)} chunks in {elapsed:.1f}s ({len(texts) / elapsed:.1f}/s)")
    return np.asarray(out, dtype=np.float32)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true", help="re-encode even when current")
    ap.add_argument("--check", action="store_true", help="verify, change nothing")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--shard", type=int, default=None,
                    help="encode only this shard (0-based); see --shards")
    ap.add_argument("--shards", type=int, default=8,
                    help="how many shards the corpus is split into")
    ap.add_argument("--merge", action="store_true",
                    help="concatenate shard files into embeddings.npy + manifest")
    ap.add_argument("--adopt", action="store_true",
                    help="re-point existing vectors at a re-ingested corpus (sampled check)")
    args = ap.parse_args()

    if not CHUNKS.exists():
        sys.exit(f"{CHUNKS} missing - run: python scripts/ingest.py")

    chunks = load_chunks()
    want = current_manifest(chunks)
    up_to_date = is_current(want)

    if args.merge:
        return merge_shards(want, args.shards)

    if args.adopt:
        return adopt_vectors(chunks, want)

    if args.check:
        if up_to_date:
            print(f"embeddings current: {want['chunks']} chunks, {want['model']}, "
                  f"corpus {want['corpus_hash'][:12]}")
            return 0
        print("embeddings missing or stale -> run: python scripts/embed.py", file=sys.stderr)
        return 1

    if up_to_date and not args.force:
        print(f"embeddings current: {want['chunks']} chunks, {want['model']}, "
              f"corpus {want['corpus_hash'][:12]} (nothing to do)")
        return 0

    if args.shard is None:
        vectors = encode(chunks, args.batch_size)
        if vectors.shape != (len(chunks), DIM):
            sys.exit(f"unexpected shape {vectors.shape}, want ({len(chunks)}, {DIM})")
        np.save(VECTORS, vectors)
        MANIFEST.write_text(json.dumps(want, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {VECTORS.relative_to(ROOT)} ({vectors.nbytes / 1e6:.1f} MB) and "
              f"{MANIFEST.relative_to(ROOT)}")
        print(f"corpus_hash {want['corpus_hash'][:12]} - quote it in every eval report")
        return 0

    return encode_shard(chunks, want, args.shard, args.shards, args.batch_size)


def shard_path(index: int) -> Path:
    return PROCESSED / f"embeddings.part{index:02d}.npy"


def shard_bounds(total: int, index: int, shards: int) -> tuple[int, int]:
    """Even split with the remainder on the last shard - no gaps, no overlap."""
    size = total // shards
    start = index * size
    end = total if index == shards - 1 else start + size
    return start, end


def encode_shard(chunks: list[dict], want: dict, index: int, shards: int,
                 batch_size: int) -> int:
    """Encode one slice in its own process.

    A long-lived encoder degrades on this machine (measured: 0.3 texts/s after an
    hour, against 22 texts/s in a fresh process), and a sharded run also survives
    interruption - a finished shard is never recomputed.
    """
    if not 0 <= index < shards:
        sys.exit(f"--shard must be 0..{shards - 1}")
    start, end = shard_bounds(len(chunks), index, shards)
    target = shard_path(index)
    if target.exists():
        existing = np.load(target)
        if existing.shape == (end - start, DIM):
            print(f"shard {index}: already encoded ({end - start} rows), skipping")
            return 0
    print(f"shard {index}/{shards - 1}: chunks {start}..{end - 1} ({end - start} rows)")
    vectors = encode(chunks[start:end], batch_size)
    if vectors.shape != (end - start, DIM):
        sys.exit(f"unexpected shape {vectors.shape} for shard {index}")
    np.save(target, vectors)
    print(f"wrote {target.name}")
    return 0


def merge_shards(want: dict, shards: int) -> int:
    total = want["chunks"]
    parts: list[np.ndarray] = []
    for index in range(shards):
        path = shard_path(index)
        if not path.exists():
            sys.exit(f"missing {path.name} - encode shards 0..{shards - 1} first")
        parts.append(np.load(path))
    vectors = np.concatenate(parts, axis=0)
    if vectors.shape != (total, DIM):
        sys.exit(f"merged shape {vectors.shape}, want ({total}, {DIM})")
    np.save(VECTORS, vectors)
    MANIFEST.write_text(json.dumps(want, indent=2) + "\n", encoding="utf-8")
    for index in range(shards):
        shard_path(index).unlink(missing_ok=True)
    print(f"merged {len(parts)} shards -> {VECTORS.relative_to(ROOT)} "
          f"({vectors.nbytes / 1e6:.1f} MB), manifest written")
    print(f"corpus_hash {want['corpus_hash'][:12]} - quote it in every eval report")
    return 0


if __name__ == "__main__":
    sys.exit(main())
