"""trade_journal feature

Revision ID: 0002_trade_journal
Revises: 0001_initial
Create Date: 2026-06-07 00:00:00
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_trade_journal"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename the old note-only trade_journal to trade_notes
    op.rename_table("trade_journal", "trade_notes")

    # Create the full-featured trade journal table
    op.create_table(
        "trade_journal",
        sa.Column("id",             sa.String(36),  primary_key=True, nullable=False),
        sa.Column("user_id",        sa.Integer,     sa.ForeignKey("users.id"),   nullable=True),
        sa.Column("signal_id",      sa.Integer,     sa.ForeignKey("signals.id"), nullable=True),
        sa.Column("symbol",         sa.String(20),  nullable=False, server_default="XAUUSD"),
        sa.Column("direction",      sa.String(10),  nullable=False),
        sa.Column("entry_price",    sa.Float,       nullable=False),
        sa.Column("exit_price",     sa.Float,       nullable=True),
        sa.Column("stop_loss",      sa.Float,       nullable=False),
        sa.Column("take_profit",    sa.Float,       nullable=False),
        sa.Column("lot_size",       sa.Float,       nullable=False),
        sa.Column("status",         sa.String(20),  nullable=False, server_default="open"),
        sa.Column("pnl_usd",        sa.Float,       nullable=True),
        sa.Column("pnl_pips",       sa.Float,       nullable=True),
        sa.Column("exit_reason",    sa.String(50),  nullable=True),
        sa.Column("emotion_rating", sa.Integer,     nullable=True),
        sa.Column("notes",          sa.Text,        nullable=True),
        sa.Column("opened_at",      sa.DateTime,    nullable=False),
        sa.Column("closed_at",      sa.DateTime,    nullable=True),
        sa.Column("created_at",     sa.DateTime,    nullable=True),
    )
    op.create_index("ix_trade_journal_id",     "trade_journal", ["id"])
    op.create_index("ix_trade_journal_status",  "trade_journal", ["status"])
    op.create_index("ix_trade_journal_symbol",  "trade_journal", ["symbol"])
    op.create_index("ix_trade_journal_user_id", "trade_journal", ["user_id"])


def downgrade() -> None:
    op.drop_table("trade_journal")
    op.rename_table("trade_notes", "trade_journal")
