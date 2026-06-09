"""Add composite indexes, updated_at columns, fix schema

Revision ID: 0005_indexes_and_timestamps
Revises: 0004_signal_enrichment
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_indexes_and_timestamps"
down_revision = "0004_signal_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── updated_at on signals ──────────────────────────────────────────────────
    op.add_column("signals", sa.Column("updated_at", sa.DateTime, nullable=True))

    # ── updated_at on users ────────────────────────────────────────────────────
    op.add_column("users", sa.Column("updated_at", sa.DateTime, nullable=True))

    # ── Composite index on candles (symbol, timeframe, timestamp) ─────────────
    # Individual indexes already exist; add composite for multi-column queries
    op.create_index(
        "ix_candle_symbol_tf_ts",
        "candles",
        ["symbol", "timeframe", "timestamp"],
        unique=False,
    )

    # ── Composite index on signals (symbol, timeframe, created_at) ────────────
    op.create_index(
        "ix_signal_symbol_tf_created",
        "signals",
        ["symbol", "timeframe", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_signal_symbol_tf_created", table_name="signals")
    op.drop_index("ix_candle_symbol_tf_ts", table_name="candles")
    op.drop_column("users", "updated_at")
    op.drop_column("signals", "updated_at")
