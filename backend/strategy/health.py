"""
Strategy health monitor: compares realised (paper/live) trade results with the
backtest reference and restricts or suspends the strategy when they diverge.

Rules (deliberately simple and explainable):
  SUSPENDED  consecutive losses ≥ max(2 × backtest max, 8)
             or current drawdown ≥ max(1.5 × backtest max DD, 8R)
             or (n ≥ 20 and z < −3)   z = (mean − ref_mean) / (ref_std / √n)
  DEGRADED   n ≥ 20 and z < −2  → risk multiplier 0.5
  INSUFFICIENT_DATA  n < min_trades (trading allowed, nothing can be concluded)
  OK         otherwise
A SUSPENDED strategy produces NO TRADE until a human resets it (new version or
explicit override) — it never re-enables itself.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Sequence

OK, INSUFFICIENT, DEGRADED, SUSPENDED = "OK", "INSUFFICIENT_DATA", "DEGRADED", "SUSPENDED"


@dataclass
class HealthReport:
    status: str
    trades: int
    expectancy_r: float | None
    current_drawdown_r: float
    consecutive_losses: int
    z_score: float | None
    risk_multiplier: float
    reasons: List[str] = field(default_factory=list)
    reference: Dict[str, float] = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def evaluate(rs: Sequence[float], reference: Dict[str, float], min_trades: int = 10) -> HealthReport:
    rs = [float(r) for r in rs]
    n = len(rs)
    ref_mean = float(reference.get("expectancy_r", 0.0))
    ref_std = float(reference.get("std_r", 1.5)) or 1.5
    ref_dd = float(reference.get("max_drawdown_r", 6.0))
    ref_cl = int(reference.get("max_consecutive_losses", 6))

    cum = peak = dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
    dd = peak - cum
    streak = 0
    for r in reversed(rs):
        if r > 0:
            break
        streak += 1

    mean = sum(rs) / n if n else None
    z = (mean - ref_mean) / (ref_std / math.sqrt(n)) if n >= 20 else None
    reasons: List[str] = []
    status, mult = (INSUFFICIENT if n < min_trades else OK), 1.0

    if streak >= max(2 * ref_cl, 8):
        reasons.append(f"{streak} ketma-ket zarar ≥ chegara {max(2 * ref_cl, 8)}")
    if dd >= max(1.5 * ref_dd, 8.0):
        reasons.append(f"Joriy drawdown {dd:.1f}R ≥ chegara {max(1.5 * ref_dd, 8.0):.1f}R")
    if z is not None and z < -3:
        reasons.append(f"Natija backtestdan statistik past (z={z:.2f} < −3)")
    if reasons:
        return HealthReport(SUSPENDED, n, _r(mean), round(dd, 2), streak, _r(z), 0.0, reasons, reference)
    if z is not None and z < -2:
        status, mult = DEGRADED, 0.5
        reasons.append(f"Natija backtestdan past (z={z:.2f} < −2) — risk 50% ga kamaytirildi")
    return HealthReport(status, n, _r(mean), round(dd, 2), streak, _r(z), mult, reasons, reference)


def _r(x):
    return None if x is None else round(x, 3)
