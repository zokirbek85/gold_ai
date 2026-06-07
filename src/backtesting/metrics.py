"""
Backtesting metrics calculator.
Computes: Win Rate, Profit Factor, Sharpe, Sortino, Max Drawdown, Avg RR, Monthly Returns.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Dict, List, Optional


class BacktestMetrics:
    def calculate(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        trades: list of {"pnl": float, "rr": float, "opened_at": datetime, "closed_at": datetime}
        Returns full metrics dict.
        """
        if not trades:
            return self._empty()

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        win_rate = len(wins) / len(pnls) * 100 if pnls else 0

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0)

        total_pnl = sum(pnls)
        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        avg_rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        sharpe = self._sharpe(pnls)
        sortino = self._sortino(pnls)
        max_dd = self._max_drawdown(pnls)
        monthly = self._monthly_returns(trades)

        return {
            "total_trades": len(trades),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 3),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "total_pnl": round(total_pnl, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "avg_rr": round(avg_rr, 2),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "monthly_returns": monthly,
        }

    @staticmethod
    def _sharpe(pnls: List[float], risk_free: float = 0.0) -> float:
        if len(pnls) < 2:
            return 0.0
        mean = sum(pnls) / len(pnls)
        variance = sum((p - mean) ** 2 for p in pnls) / len(pnls)
        std = math.sqrt(variance)
        if std == 0:
            return 0.0
        return (mean - risk_free) / std * math.sqrt(252)

    @staticmethod
    def _sortino(pnls: List[float], risk_free: float = 0.0) -> float:
        if len(pnls) < 2:
            return 0.0
        mean = sum(pnls) / len(pnls)
        downside = [p for p in pnls if p < risk_free]
        if not downside:
            return float("inf")
        downside_var = sum((p - risk_free) ** 2 for p in downside) / len(downside)
        downside_std = math.sqrt(downside_var)
        if downside_std == 0:
            return 0.0
        return (mean - risk_free) / downside_std * math.sqrt(252)

    @staticmethod
    def _max_drawdown(pnls: List[float]) -> float:
        if not pnls:
            return 0.0
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for pnl in pnls:
            equity += pnl
            if equity > peak:
                peak = equity
            dd = (peak - equity) / (peak + 1e-9)
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @staticmethod
    def _monthly_returns(trades: List[Dict[str, Any]]) -> Dict[str, float]:
        monthly: Dict[str, float] = {}
        for t in trades:
            dt = t.get("closed_at") or t.get("opened_at")
            if dt is None:
                continue
            if isinstance(dt, str):
                try:
                    dt = datetime.fromisoformat(dt)
                except ValueError:
                    continue
            key = dt.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0.0) + t["pnl"]
        return {k: round(v, 2) for k, v in sorted(monthly.items())}

    @staticmethod
    def _empty() -> Dict[str, Any]:
        return {
            "total_trades": 0, "win_rate": 0, "profit_factor": 0,
            "sharpe_ratio": 0, "sortino_ratio": 0, "max_drawdown_pct": 0,
            "total_pnl": 0, "gross_profit": 0, "gross_loss": 0,
            "avg_win": 0, "avg_loss": 0, "avg_rr": 0,
            "winning_trades": 0, "losing_trades": 0, "monthly_returns": {},
        }


backtest_metrics = BacktestMetrics()
