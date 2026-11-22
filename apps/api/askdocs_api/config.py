"""Typed configuration, read once at boot.

The `.env.example` contract is the source of truth; a missing required value
fails at import with the variable's own name (pydantic reports the field alias),
not with a stack trace three layers deep inside a query.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# `.env` lives at the repo root, but the API, alembic and the eval harness all
# start from different working directories. Anchoring it to this file means the
# env contract is found once, not re-derived per entry point.
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Every knob the API reads. Defaults mirror `.env.example`."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore"
    )

    # --- database ---------------------------------------------------------
    database_url: str = Field(alias="DATABASE_URL")
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")

    # --- corpus / models --------------------------------------------------
    corpus_chunks: str = Field(default="data/processed/chunks.jsonl", alias="CORPUS_CHUNKS")
    embed_model: str = Field(default="BAAI/bge-small-en-v1.5", alias="EMBED_MODEL")
    embed_dim: int = Field(default=384, alias="EMBED_DIM")
    rerank_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2", alias="RERANK_MODEL"
    )

    # --- retrieval --------------------------------------------------------
    dense_top_k: int = Field(default=50, alias="DENSE_TOP_K")
    lexical_top_k: int = Field(default=50, alias="LEXICAL_TOP_K")
    # rarest-N lexemes kept for the full-text query (see lexical_search)
    lexical_terms: int = Field(default=4, alias="LEXICAL_TERMS")
    rrf_k: int = Field(default=60, alias="RRF_K")
    rerank_candidates: int = Field(default=30, alias="RERANK_CANDIDATES")
    rerank_top_k: int = Field(default=6, alias="RERANK_TOP_K")
    refusal_score_threshold: float = Field(default=0.35, alias="REFUSAL_SCORE_THRESHOLD")

    # --- product ----------------------------------------------------------
    web_origin: str = Field(default="http://localhost:3000", alias="WEB_ORIGIN")
    rate_limit_per_min: int = Field(default=20, alias="RATE_LIMIT_PER_MIN")
    debug_enabled: bool = Field(default=True, alias="DEBUG_ENABLED")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
