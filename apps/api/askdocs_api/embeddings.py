"""In-process embeddings: `bge-small-en-v1.5`, 384-d, normalised, no API key.

Determinism is the point (ADR-004): the same text must produce the same vector
on every machine, or eval numbers stop being comparable. The model is loaded
once per process and reused; the first call is the slow one.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any

import numpy as np

from askdocs_api.config import get_settings


@lru_cache(maxsize=1)
def _model() -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embed_model, device="cpu")


def model_name() -> str:
    return get_settings().embed_model


def dimension() -> int:
    return get_settings().embed_dim


def embed_passages(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Embed documents. `bge` wants passages plain and queries prefixed."""
    if not texts:
        return np.zeros((0, dimension()), dtype=np.float32)
    vectors = _model().encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return np.asarray(vectors, dtype=np.float32)


def embed_query(text: str) -> np.ndarray:
    """bge-small is trained with this instruction prefix on the query side only."""
    prefix = "Represent this sentence for searching relevant passages: "
    vectors = embed_passages([prefix + text])
    return np.asarray(vectors[0], dtype=np.float32)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def manifest(chunk_count: int, corpus_hash: str) -> dict[str, Any]:
    """What a vector set was built from - a model change must be detectable."""
    return {
        "model": model_name(),
        "dimension": dimension(),
        "chunks": chunk_count,
        "corpus_hash": corpus_hash,
        "normalised": True,
        "query_prefix": "Represent this sentence for searching relevant passages: ",
    }
