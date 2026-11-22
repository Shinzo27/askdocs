"""SQLAlchemy models — the schema in `docs/ARCHITECTURE.md`, nothing more.

`citations` is a real table rather than a JSON blob on the message, because the
feedback loop's question ("which section gets flagged most often?") is a
GROUP BY, not a parsing exercise.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(Text, nullable=False)  # act | rules | faq | circular
    publisher: Mapped[str | None] = mapped_column(Text)
    vintage: Mapped[str | None] = mapped_column(Text)
    applies_to_ay: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    pages: Mapped[int | None] = mapped_column(Integer)
    sections_unparsed: Mapped[int | None] = mapped_column(Integer)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # "it-act-1961:80C:0"
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"))
    section: Mapped[str | None] = mapped_column(Text)
    section_title: Mapped[str | None] = mapped_column(Text)
    chapter: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chars: Mapped[int] = mapped_column(Integer, nullable=False)
    # repeal note rather than live provision; excluded from retrieval
    omitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                          server_default="false")
    embedding: Mapped[Any] = mapped_column(Vector(384))
    tsv: Mapped[Any] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True)
    )

    document: Mapped[Document] = relationship(lazy="joined")

    __table_args__ = (
        Index("chunks_section_idx", "doc_id", "section"),
        Index("chunks_tsv_idx", "tsv", postgresql_using="gin"),
        Index(
            "chunks_embedding_idx",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(Text)
    citation_valid: Mapped[bool | None] = mapped_column(Boolean)
    refused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    cost_inr: Mapped[Any | None] = mapped_column(Numeric(10, 4))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Citation(Base):
    __tablename__ = "citations"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    marker: Mapped[int] = mapped_column(Integer, primary_key=True)  # the [n] the reader sees
    chunk_id: Mapped[str] = mapped_column(Text, nullable=False)
    doc_id: Mapped[str] = mapped_column(Text, nullable=False)
    section: Mapped[str | None] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    rerank_score: Mapped[float | None] = mapped_column(Float)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QueryLog(Base):
    """One row per request: the table the README's numbers are computed from."""

    __tablename__ = "query_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    doc_scope: Mapped[Any | None] = mapped_column(JSONB)
    candidates: Mapped[int | None] = mapped_column(Integer)
    fused: Mapped[int | None] = mapped_column(Integer)
    reranked: Mapped[int | None] = mapped_column(Integer)
    top_score: Mapped[float | None] = mapped_column(Float)
    retrieved_sections: Mapped[Any | None] = mapped_column(JSONB)
    latency_ms: Mapped[Any | None] = mapped_column(JSONB)  # {"retrieve":..,"rerank":..}
    tokens: Mapped[Any | None] = mapped_column(JSONB)
    provider: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    citation_valid: Mapped[bool | None] = mapped_column(Boolean)
    refused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    corpus_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
