"""signal outcome tracking (additive: nullable columns on signals)

Revision ID: 0007_signal_outcomes
Revises: 0006_paper_trading
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_signal_outcomes"
down_revision = "0006_paper_trading"
branch_labels = None
depends_on = None

COLUMNS = [
    ("outcome", sa.String(24)), ("outcome_r", sa.Float), ("mfe_r", sa.Float), ("mae_r", sa.Float),
    ("tp1_hit", sa.Boolean), ("fill_price", sa.Float), ("fill_time", sa.DateTime),
    ("exit_price", sa.Float), ("exit_time", sa.DateTime), ("resolved_at", sa.DateTime),
    ("resolution_tf", sa.String(10)), ("data_gap", sa.Boolean),
]


def upgrade() -> None:
    for name, typ in COLUMNS:
        op.add_column("signals", sa.Column(name, typ, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("signals", name)
