"""
Strategy laboratory — several strategy families compared under ONE harness:
same clean data, same costs, same execution (strategy.backtest.simulate), same
train/test split and walk-forward windows.

Parameters below were fixed BEFORE running (textbook defaults, no grid search)
to limit overfitting. Every strategy returns the same decision dict, so any of
them can later be served live through the same pipeline.

Families:
  trend_pullback   v2 engine (strategy.engine.evaluate_bar)
  donchian_break   close beyond the prior 20-bar range, context not opposing
  ts_momentum      60-bar momentum turns positive/negative with EMA alignment
  mean_reversion   RANGE regime, close outside BB(20,2) + RSI extreme, TP = BB mid
  squeeze_break    BB-width in bottom 20 % of last 100 bars, then 20-bar breakout
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Dict, Optional

import numpy as np
import pandas as pd

from strategy import indicators as ind
from strategy.config import RiskConfig, StrategyConfig
from strategy.engine import BUY, SELL, classify_regime, evaluate_bar

Decider = Callable[[int], Optional[Dict[str, Any]]]


def enrich(p: pd.DataFrame) -> pd.DataFrame:
    """Extra causal columns used by the non-v2 families."""
    x = p.copy()
    c = x["close"]
    x["don_hi"] = x["high"].shift(1).rolling(20, min_periods=20).max()
    x["don_lo"] = x["low"].shift(1).rolling(20, min_periods=20).min()
    mid = c.rolling(20, min_periods=20).mean()
    sd = c.rolling(20, min_periods=20).std(ddof=0)
    x["bb_mid"], x["bb_up"], x["bb_lo"] = mid, mid + 2 * sd, mid - 2 * sd
    width = (x["bb_up"] - x["bb_lo"]) / mid
    x["bb_width_pct"] = width.rolling(100, min_periods=100).rank(pct=True)
    x["mom"] = c / c.shift(60) - 1
    return x


def _levels(side: str, entry: float, risk: float, rr: float):
    s = 1 if side == BUY else -1
    return entry - s * risk, entry + s * rr * risk


def _common_block(row, cfg: StrategyConfig, risk_cfg: RiskConfig) -> Optional[str]:
    """Blocks shared by every family (same NO TRADE protections)."""
    reg = classify_regime(row, cfg)
    if reg == "INSUFFICIENT_DATA":
        return "INSUFFICIENT_HISTORY"
    hour = pd.Timestamp(row["close_time"]).hour
    if cfg.rollover_start_utc <= hour < cfg.rollover_end_utc:
        return "ROLLOVER_SESSION"
    if risk_cfg.spread > risk_cfg.max_spread:
        return "SPREAD_TOO_HIGH"
    return None


def _finalize(side, entry, risk, rr, row, cfg, risk_cfg, name, regime):
    atr = row["atr"]
    if not np.isfinite(risk) or risk <= 0 or risk > cfg.sl_max_atr * atr:
        return {"action": "NO TRADE", "reason_codes": ["SL_TOO_WIDE"]}
    risk = max(risk, cfg.sl_min_atr * atr)
    if risk_cfg.spread / risk > risk_cfg.max_spread_to_risk:
        return {"action": "NO TRADE", "reason_codes": ["SPREAD_TOO_HIGH_VS_SL"]}
    cost = risk_cfg.spread + 2 * risk_cfg.slippage
    if (rr * risk - cost) / (risk + cost) < min(cfg.min_rr, rr * 0.9):
        return {"action": "NO TRADE", "reason_codes": ["RR_TOO_LOW"]}
    sl, tp = _levels(side, entry, risk, rr)
    return {"action": side, "entry": entry, "stop_loss": sl, "take_profit": tp,
            "regime": regime, "strategy": name}


def make_decider(name: str, p: pd.DataFrame, cfg: StrategyConfig, risk_cfg: RiskConfig) -> Decider:
    if name == "trend_pullback":
        def d(i):
            out = evaluate_bar(p, i, cfg, risk_cfg).to_dict()
            out["strategy"] = name
            return out
        return d

    x = enrich(p)
    cols = {k: x[k].to_numpy() for k in x.columns if x[k].dtype != object}
    trend = x["c_trend"].to_numpy()

    def d(i):
        if i < 2:
            return None
        row = x.iloc[i]
        blk = _common_block(row, cfg, risk_cfg)
        if blk:
            return {"action": "NO TRADE", "reason_codes": [blk]}
        regime = classify_regime(row, cfg)
        c, o, atr = cols["close"][i], cols["open"][i], cols["atr"][i]
        if regime == "HIGH_VOLATILITY" and name != "squeeze_break":
            return {"action": "NO TRADE", "reason_codes": ["VOLATILITY_TOO_HIGH"]}

        if name == "donchian_break":
            if np.isnan(cols["don_hi"][i]):
                return None
            if c > cols["don_hi"][i] and trend[i] != "DOWN":
                return _finalize(BUY, c, 2.0 * atr, 2.0, row, cfg, risk_cfg, name, regime)
            if c < cols["don_lo"][i] and trend[i] != "UP":
                return _finalize(SELL, c, 2.0 * atr, 2.0, row, cfg, risk_cfg, name, regime)
            return {"action": "NO TRADE", "reason_codes": ["NO_BREAKOUT"]}

        if name == "ts_momentum":
            m, m1 = cols["mom"][i], cols["mom"][i - 1]
            if np.isnan(m) or np.isnan(m1) or cols["adx"][i] < 20:
                return {"action": "NO TRADE", "reason_codes": ["NO_MOMENTUM"]}
            if m > 0 >= m1 and cols["ema_fast"][i] > cols["ema_slow"][i]:
                return _finalize(BUY, c, 2.0 * atr, 3.0, row, cfg, risk_cfg, name, regime)
            if m < 0 <= m1 and cols["ema_fast"][i] < cols["ema_slow"][i]:
                return _finalize(SELL, c, 2.0 * atr, 3.0, row, cfg, risk_cfg, name, regime)
            return {"action": "NO TRADE", "reason_codes": ["NO_MOMENTUM_FLIP"]}

        if name == "mean_reversion":
            if regime != "RANGE" or np.isnan(cols["bb_mid"][i]):
                return {"action": "NO TRADE", "reason_codes": ["NOT_RANGE"]}
            mid = cols["bb_mid"][i]
            if cols["low"][i] < cols["bb_lo"][i] and cols["rsi"][i] < 30 and c > o:
                risk = 1.5 * atr
                return _finalize(BUY, c, risk, max((mid - c) / risk, 0.0), row, cfg, risk_cfg, name, regime)
            if cols["high"][i] > cols["bb_up"][i] and cols["rsi"][i] > 70 and c < o:
                risk = 1.5 * atr
                return _finalize(SELL, c, risk, max((c - mid) / risk, 0.0), row, cfg, risk_cfg, name, regime)
            return {"action": "NO TRADE", "reason_codes": ["NO_EXTREME"]}

        if name == "squeeze_break":
            if np.isnan(cols["bb_width_pct"][i - 1]) or np.isnan(cols["don_hi"][i]):
                return None
            if cols["bb_width_pct"][i - 1] > 0.2:
                return {"action": "NO TRADE", "reason_codes": ["NO_SQUEEZE"]}
            if c > cols["don_hi"][i]:
                return _finalize(BUY, c, 1.5 * atr, 2.5, row, cfg, risk_cfg, name, regime)
            if c < cols["don_lo"][i]:
                return _finalize(SELL, c, 1.5 * atr, 2.5, row, cfg, risk_cfg, name, regime)
            return {"action": "NO TRADE", "reason_codes": ["NO_BREAKOUT"]}
        raise ValueError(name)
    return d


FAMILIES = ["trend_pullback", "donchian_break", "ts_momentum", "mean_reversion", "squeeze_break"]


def default_cfg(primary_tf: int, context_tf: int) -> StrategyConfig:
    return replace(StrategyConfig(), primary_tf=primary_tf, context_tf=context_tf)
