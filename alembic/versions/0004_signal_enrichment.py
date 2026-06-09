"""Add signal enrichment columns

Revision ID: 0004_signal_enrichment
Revises: 0003_prediction_feedback
Create Date: 2026-06-09 00:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_signal_enrichment"
down_revision = "0003_prediction_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("signals", sa.Column("lot_size",          sa.Float, nullable=True))
    op.add_column("signals", sa.Column("risk_amount_usd",   sa.Float, nullable=True))
    op.add_column("signals", sa.Column("plain_explanation", sa.Text,  nullable=True))
    op.add_column("signals", sa.Column("signal_emoji",      sa.String(4), nullable=True))
    op.add_column("signals", sa.Column("sl_distance_pct",   sa.Float, nullable=True))
    op.add_column("signals", sa.Column("tp1_distance_pct",  sa.Float, nullable=True))
    op.add_column("signals", sa.Column("tp2_distance_pct",  sa.Float, nullable=True))
    op.add_column("signals", sa.Column("tp3_distance_pct",  sa.Float, nullable=True))


def downgrade() -> None:
    op.drop_column("signals", "tp3_distance_pct")
    op.drop_column("signals", "tp2_distance_pct")
    op.drop_column("signals", "tp1_distance_pct")
    op.drop_column("signals", "sl_distance_pct")
    op.drop_column("signals", "signal_emoji")
    op.drop_column("signals", "plain_explanation")
    op.drop_column("signals", "risk_amount_usd")
    op.drop_column("signals", "lot_size")
