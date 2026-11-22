"""Initial schema: documents, chunks (+vector/tsvector), product tables, corpus_meta.

Revision ID: 0001
Revises: none
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

EMBED_DIM = 384


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("doc_id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("doc_type", sa.Text(), nullable=False),
        sa.Column("publisher", sa.Text()),
        sa.Column("vintage", sa.Text()),
        sa.Column("applies_to_ay", sa.Text()),
        sa.Column("source_url", sa.Text()),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("pages", sa.Integer()),
        sa.Column("sections_unparsed", sa.Integer()),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("doc_id", sa.Text(), sa.ForeignKey("documents.doc_id", ondelete="CASCADE")),
        sa.Column("section", sa.Text()),
        sa.Column("section_title", sa.Text()),
        sa.Column("chapter", sa.Text()),
        sa.Column("page", sa.Integer()),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chars", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(EMBED_DIM)),
        sa.Column(
            "tsv",
            TSVECTOR,
            sa.Computed("to_tsvector('english', text)", persisted=True),
        ),
    )
    op.create_index("chunks_section_idx", "chunks", ["doc_id", "section"])
    op.execute("CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv)")
    # HNSW needs data before it is worth building; created explicitly so a
    # 11k-row load does not pay index maintenance per insert.
    op.execute(
        "CREATE INDEX chunks_embedding_idx ON chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "conversations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.Text(), nullable=False, index=True),
        sa.Column("title", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.Text()),
        sa.Column("provider", sa.Text()),
        sa.Column("citation_valid", sa.Boolean()),
        sa.Column("refused", sa.Boolean(), server_default="false"),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("cost_inr", sa.Numeric(10, 4)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "citations",
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("marker", sa.Integer(), primary_key=True),
        sa.Column("chunk_id", sa.Text(), nullable=False),
        sa.Column("doc_id", sa.Text(), nullable=False),
        sa.Column("section", sa.Text()),
        sa.Column("page", sa.Integer()),
        sa.Column("rerank_score", sa.Float()),
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "query_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(32), unique=True, nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("doc_scope", JSONB()),
        sa.Column("candidates", sa.Integer()),
        sa.Column("fused", sa.Integer()),
        sa.Column("reranked", sa.Integer()),
        sa.Column("top_score", sa.Float()),
        sa.Column("retrieved_sections", JSONB()),
        sa.Column("latency_ms", JSONB()),
        sa.Column("tokens", JSONB()),
        sa.Column("provider", sa.Text()),
        sa.Column("model", sa.Text()),
        sa.Column("citation_valid", sa.Boolean()),
        sa.Column("refused", sa.Boolean(), server_default="false"),
        sa.Column("corpus_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    op.create_table(
        "corpus_meta",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for table in (
        "corpus_meta",
        "query_log",
        "feedback",
        "citations",
        "messages",
        "conversations",
        "chunks",
        "documents",
    ):
        op.drop_table(table)
    op.execute("DROP EXTENSION IF EXISTS vector")
