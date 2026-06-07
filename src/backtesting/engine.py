"""
Backtesting engine.
Runs the signal scorer over historical candle data (walk-forward simulation).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.backtesting.metrics import backtest_metrics
from src.risk_management.calculator import risk_calculator
from src.signals.scorer import signal_scorer

log = logging.getLogger(__name__)


class BacktestEngine:
    def run(
        self,
        candles: List[Dict[str, Any]],
        window: int = 100,
        step: int = 1,
        account_balance: float = 10000.0,
        name: str = "backtest",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Walk-forward backtest over the candle series.

        For each position i (window..len(candles)):
          1. Generate a signal on candles[i-window:i]
          2. If BUY/SELL: simulate the trade on candles[i:]
          3. Record PnL when TP or SL is hit (or end of data)
        """
        if len(candles) < window + 10:
            return {"error": f"Need at least {window + 10} candles, got {len(candles)}"}

        trades: List[Dict[str, Any]] = []
        equity = account_balance
        equity_curve: List[float] = [account_balance]

        for i in range(window, len(candles), step):
            history = candles[:i]
            signal = signal_scorer.generate(history, account_balance=equity)

            if signal["signal_type"] not in ("BUY", "SELL"):
                continue

            entry = signal.get("entry")
            sl = signal.get("stop_loss")
            tp = signal.get("take_profit")
            lot_size = signal.get("lot_size", 0.01)

            if entry is None or sl is None or tp is None:
                continue

            direction = signal["direction"]
            trade_result = self._simulate_trade(
                candles=candles[i:],
                entry=entry,
                sl=sl,
                tp=tp,
                direction=direction,
                lot_size=lot_size,
            )
            if trade_result is None:
                continue

            pnl_usd = trade_result["pnl_pips"] * lot_size * 0.01  # simplified PnL
            equity += pnl_usd
            equity_curve.append(equity)

            trades.append({
                "pnl": pnl_usd,
                "pnl_pips": trade_result["pnl_pips"],
                "rr": signal.get("risk_reward", 0),
                "direction": direction,
                "signal_type": signal["signal_type"],
                "opened_at": _candle_time(candles[i - 1]),
                "closed_at": trade_result.get("closed_at"),
                "exit_reason": trade_result.get("exit_reason"),
                "confidence": signal.get("confidence", 0),
            })

        metrics = backtest_metrics.calculate(trades)
        return {
            "name": name,
            "parameters": parameters or {"window": window, "step": step},
            "metrics": metrics,
            "trades": trades,
            "equity_curve": equity_curve,
            "candle_count": len(candles),
            "trade_count": len(trades),
            "created_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _simulate_trade(
        candles: List[Dict[str, Any]],
        entry: float,
        sl: float,
        tp: float,
        direction: str,
        lot_size: float,
    ) -> Optional[Dict[str, Any]]:
        sl_dist = abs(entry - sl)
        if sl_dist == 0:
            return None

        for i, candle in enumerate(candles[:100]):
            high = float(candle["high"])
            low = float(candle["low"])

            if direction == "bullish":
                if low <= sl:
                    pnl_pips = -(sl_dist / 0.01)
                    return {"pnl_pips": pnl_pips, "exit_reason": "SL", "closed_at": _candle_time(candle)}
                if high >= tp:
                    pnl_pips = abs(tp - entry) / 0.01
                    return {"pnl_pips": pnl_pips, "exit_reason": "TP", "closed_at": _candle_time(candle)}
            else:
                if high >= sl:
                    pnl_pips = -(sl_dist / 0.01)
                    return {"pnl_pips": pnl_pips, "exit_reason": "SL", "closed_at": _candle_time(candle)}
                if low <= tp:
                    pnl_pips = abs(entry - tp) / 0.01
                    return {"pnl_pips": pnl_pips, "exit_reason": "TP", "closed_at": _candle_time(candle)}

        # Closed at last bar
        last_close = float(candles[-1]["close"]) if candles else entry
        if direction == "bullish":
            pnl_pips = (last_close - entry) / 0.01
        else:
            pnl_pips = (entry - last_close) / 0.01
        return {"pnl_pips": pnl_pips, "exit_reason": "EOD", "closed_at": _candle_time(candles[-1]) if candles else None}


def _candle_time(candle: Dict[str, Any]) -> Optional[str]:
    ts = candle.get("timestamp") or candle.get("time")
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)


backtest_engine = BacktestEngine()
