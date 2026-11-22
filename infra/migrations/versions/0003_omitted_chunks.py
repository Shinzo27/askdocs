"""Flag omitted provisions so retrieval can skip them.

Revision ID: 0003
Revises: 0002

A repealed section keeps its note in the statute PDF ("Omitted by the Finance Act,
1985"), and that note matches a question about the topic perfectly while being
useless as an answer. `ingest.py` flags it; retrieval filters on it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("omitted", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("chunks_omitted_idx", "chunks", ["omitted"])


def downgrade() -> None:
    op.drop_index("chunks_omitted_idx", table_name="chunks")
    op.drop_column("chunks", "omitted")
