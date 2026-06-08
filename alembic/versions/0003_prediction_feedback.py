"""Add prediction feedback tables

Revision ID: 0003_prediction_feedback
Revises: 0002_trade_journal
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_prediction_feedback"
down_revision = "0002_trade_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("predicted_at", sa.DateTime, nullable=False),
        sa.Column("candle_time", sa.DateTime, nullable=False),
        sa.Column("current_price", sa.Float, nullable=False),
        sa.Column("predicted_dir", sa.String(10), nullable=False),
        sa.Column("buy_pct", sa.Float),
        sa.Column("sell_pct", sa.Float),
        sa.Column("neutral_pct", sa.Float),
        sa.Column("confidence", sa.Float),
        sa.Column("look_ahead", sa.Integer, default=12),
        sa.Column("features_json", sa.Text),
        sa.Column("outcome_checked", sa.Boolean, default=False),
    )
    op.create_index("ix_predlog_symbol", "prediction_log", ["symbol"])
    op.create_index("ix_predlog_predicted_at", "prediction_log", ["predicted_at"])
    op.create_index("ix_predlog_checked", "prediction_log", ["outcome_checked"])
    op.create_index(
        "ix_predlog_sym_tf_checked",
        "prediction_log",
        ["symbol", "timeframe", "outcome_checked"],
    )

    op.create_table(
        "prediction_result",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("prediction_id", sa.Integer, nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("predicted_at", sa.DateTime, nullable=False),
        sa.Column("resolved_at", sa.DateTime),
        sa.Column("predicted_dir", sa.String(10), nullable=False),
        sa.Column("actual_dir", sa.String(10), nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=False),
        sa.Column("price_change_pct", sa.Float, nullable=False),
        sa.Column("was_correct", sa.Boolean, nullable=False),
        sa.Column("market_volatility", sa.Float),
        sa.Column("trend_strength", sa.Float),
        sa.Column("rsi_at_signal", sa.Float),
        sa.Column("session", sa.String(20)),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_predresult_symbol", "prediction_result", ["symbol"])
    op.create_index("ix_predresult_was_correct", "prediction_result", ["was_correct"])
    op.create_index("ix_predresult_sym_tf", "prediction_result", ["symbol", "timeframe"])

    op.create_table(
        "error_pattern",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("detected_at", sa.DateTime),
        sa.Column("pattern_type", sa.String(50), nullable=False),
        sa.Column("rsi_range_low", sa.Float),
        sa.Column("rsi_range_high", sa.Float),
        sa.Column("adx_range_low", sa.Float),
        sa.Column("adx_range_high", sa.Float),
        sa.Column("volatility_low", sa.Float),
        sa.Column("volatility_high", sa.Float),
        sa.Column("session", sa.String(20)),
        sa.Column("was_predicted", sa.String(10)),
        sa.Column("correct_was", sa.String(10)),
        sa.Column("occurrence_count", sa.Integer, default=1),
        sa.Column("error_rate", sa.Float),
        sa.Column("weight_penalty", sa.Float, default=0.1),
        sa.Column("description", sa.Text),
    )
    op.create_index("ix_errpat_symbol", "error_pattern", ["symbol"])
    op.create_index("ix_errpat_pattern_type", "error_pattern", ["pattern_type"])
    op.create_index("ix_errpat_sym_type", "error_pattern", ["symbol", "pattern_type"])


def downgrade() -> None:
    op.drop_table("error_pattern")
    op.drop_table("prediction_result")
    op.drop_table("prediction_log")
