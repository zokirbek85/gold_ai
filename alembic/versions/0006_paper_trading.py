"""paper trading ledger (additive: new tables only)

Revision ID: 0006_paper_trading
Revises: 0005_indexes_and_timestamps
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_paper_trading"
down_revision = "0005_indexes_and_timestamps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "paper_accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("mode", sa.String(10), nullable=False, server_default="paper"),
        sa.Column("start_balance", sa.Float, nullable=False),
        sa.Column("balance", sa.Float, nullable=False),
        sa.Column("peak_balance", sa.Float, nullable=False),
        sa.Column("halted", sa.Boolean, server_default=sa.false()),
        sa.Column("halt_reason", sa.String(200)),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )
    op.create_table(
        "paper_trades",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("paper_accounts.id"), nullable=False, index=True),
        sa.Column("signal_key", sa.String(120), nullable=False),
        sa.Column("signal_id", sa.Integer),
        sa.Column("strategy", sa.String(40), nullable=False),
        sa.Column("strategy_version", sa.String(20), nullable=False),
        sa.Column("config_hash", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(4), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, index=True),
        sa.Column("regime", sa.String(30)),
        sa.Column("signal_time", sa.DateTime, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        *[sa.Column(c, sa.Float, nullable=False) for c in
          ("entry_ref", "zone_low", "zone_high", "stop_loss", "take_profit", "risk_per_oz", "lots", "spread", "slippage")],
        *[sa.Column(c, sa.Float) for c in ("fill_price", "exit_price", "r_multiple", "pnl_usd", "costs_usd")],
        sa.Column("fill_time", sa.DateTime),
        sa.Column("exit_time", sa.DateTime),
        sa.Column("exit_reason", sa.String(30)),
        sa.Column("mfe_r", sa.Float), sa.Column("mae_r", sa.Float),
        sa.Column("bars_processed", sa.Integer), sa.Column("open_minutes", sa.Integer),
        sa.Column("last_bar", sa.DateTime), sa.Column("data_gap", sa.Boolean),
        sa.Column("reasons", sa.Text),
        sa.Column("created_at", sa.DateTime), sa.Column("updated_at", sa.DateTime),
        sa.UniqueConstraint("account_id", "signal_key", name="uq_paper_signal"),
    )


def downgrade() -> None:
    op.drop_table("paper_trades")
    op.drop_table("paper_accounts")
