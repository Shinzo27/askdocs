"""Lexeme document-frequency statistics for the lexical retriever.

Revision ID: 0002
Revises: 0001

`ts_rank_cd` scores term frequency and proximity but has no notion of rarity, so
an OR-query for a question like "how much can I deduct under 80C for tuition fees"
ranked chunks that merely say "deduction" above the twelve chunks that say "80C".
Postgres only exposes document frequency through `ts_stat`, which is a scan - so
it is materialised here, rebuilt by the loader, and joined per query.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lexeme_stats",
        sa.Column("lexeme", sa.Text(), primary_key=True),
        sa.Column("ndoc", sa.Integer(), nullable=False),
        sa.Column("nentry", sa.Integer(), nullable=False),
    )
    op.create_index("lexeme_stats_ndoc_idx", "lexeme_stats", ["ndoc"])


def downgrade() -> None:
    op.drop_table("lexeme_stats")
