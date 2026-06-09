"""
MarketRegimeDetector — classifies the current market regime from OHLCV candles.

Regimes:
  TRENDING_UP     — strong directional uptrend
  TRENDING_DOWN   — strong directional downtrend
  RANGING         — price oscillates in a band
  VOLATILE        — unusually high ATR relative to recent average
  LOW_VOLATILITY  — unusually low ATR (pre-breakout compression)
  NEWS_DRIVEN     — regime inferred externally (injected from news score)

Usage:
    detector = MarketRegimeDetector()
    regime = detector.detect(candles)
    # regime.name, regime.strength (0–100), regime.description
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class Regime:
    name: str          # e.g. "TRENDING_UP"
    strength: float    # 0–100; higher = more conviction
    description: str
    adx: float = 0.0
    volatility_ratio: float = 0.0


class MarketRegimeDetector:
    """
    Lightweight, dependency-free regime classifier.

    Uses:
      - ADX (Average Directional Index) for trend strength
      - ATR relative to 50-period average ATR for volatility regime
      - Price range / midpoint ratio for ranging detection
    """

    ADX_TRENDING_THRESHOLD: float = 25.0
    ADX_STRONG_THRESHOLD:   float = 40.0
    VOL_HIGH_MULTIPLIER:    float = 1.5   # ATR > 1.5× avg → volatile
    VOL_LOW_MULTIPLIER:     float = 0.6   # ATR < 0.6× avg → low-vol
    RANGE_LOOKBACK:         int   = 20

    def detect(self, candles: List[Dict[str, Any]], news_driven: bool = False) -> Regime:
        """
        Primary entry point.
        candles: list of dicts with keys open/high/low/close.
        news_driven: True when a high-impact economic event was detected.
        """
        if news_driven:
            return Regime(
                name="NEWS_DRIVEN",
                strength=80.0,
                description="High-impact news event active — signals suppressed",
            )

        n = len(candles)
        if n < 30:
            return Regime(name="RANGING", strength=50.0, description="Insufficient data")

        adx_val   = self._adx(candles)
        atr_now   = self._atr(candles[-15:])
        atr_avg   = self._atr(candles[-50:]) if n >= 50 else atr_now
        vol_ratio = (atr_now / atr_avg) if atr_avg > 0 else 1.0

        # Volatile regime takes priority over trend
        if vol_ratio > self.VOL_HIGH_MULTIPLIER:
            return Regime(
                name="VOLATILE",
                strength=round(min(100, (vol_ratio - 1) * 100), 1),
                description=f"ATR {vol_ratio:.1f}× above average — volatile market",
                adx=adx_val,
                volatility_ratio=vol_ratio,
            )

        if vol_ratio < self.VOL_LOW_MULTIPLIER:
            return Regime(
                name="LOW_VOLATILITY",
                strength=round(min(100, (1 - vol_ratio) * 100), 1),
                description=f"ATR {vol_ratio:.1f}× below average — compression, potential breakout",
                adx=adx_val,
                volatility_ratio=vol_ratio,
            )

        # Trend detection via ADX + slope
        if adx_val >= self.ADX_TRENDING_THRESHOLD:
            slope = self._price_slope(candles[-20:])
            if slope > 0:
                strength = round(min(100.0, adx_val * 1.5), 1)
                return Regime(
                    name="TRENDING_UP",
                    strength=strength,
                    description=f"ADX {adx_val:.1f} — uptrend",
                    adx=adx_val,
                    volatility_ratio=vol_ratio,
                )
            else:
                strength = round(min(100.0, adx_val * 1.5), 1)
                return Regime(
                    name="TRENDING_DOWN",
                    strength=strength,
                    description=f"ADX {adx_val:.1f} — downtrend",
                    adx=adx_val,
                    volatility_ratio=vol_ratio,
                )

        # Default: ranging
        range_pct = self._range_pct(candles[-self.RANGE_LOOKBACK:])
        strength  = round(max(0, 100 - adx_val * 2), 1)
        return Regime(
            name="RANGING",
            strength=strength,
            description=f"ADX {adx_val:.1f} — ranging, price swing {range_pct:.2f}%",
            adx=adx_val,
            volatility_ratio=vol_ratio,
        )

    # ── SMC/Signal weight adjustments based on regime ─────────────────────────

    def signal_weights(self, regime: Regime) -> Dict[str, float]:
        """
        Return adjusted component weights for the signal engine.
        Maps regime name → weight overrides (only changed keys included).
        """
        base = {"technical": 0.35, "smc": 0.25, "ml": 0.20, "news": 0.10, "economic": 0.10}

        if regime.name == "TRENDING_UP":
            return {**base, "technical": 0.40, "smc": 0.20}
        if regime.name == "TRENDING_DOWN":
            return {**base, "technical": 0.40, "smc": 0.20}
        if regime.name == "RANGING":
            return {**base, "smc": 0.35, "technical": 0.25}
        if regime.name == "VOLATILE":
            return {**base, "ml": 0.25, "technical": 0.30}
        if regime.name == "LOW_VOLATILITY":
            return {**base, "smc": 0.30, "ml": 0.25, "technical": 0.25}
        if regime.name == "NEWS_DRIVEN":
            return {**base, "news": 0.30, "economic": 0.25, "technical": 0.20, "smc": 0.15, "ml": 0.10}
        return base

    # ── Indicators ────────────────────────────────────────────────────────────

    def _atr(self, candles: List[Dict], period: int = 14) -> float:
        if len(candles) < 2:
            return 0.0
        trs: List[float] = []
        for i in range(1, len(candles)):
            hl = float(candles[i]["high"]) - float(candles[i]["low"])
            hc = abs(float(candles[i]["high"]) - float(candles[i - 1]["close"]))
            lc = abs(float(candles[i]["low"])  - float(candles[i - 1]["close"]))
            trs.append(max(hl, hc, lc))
        if not trs:
            return 0.0
        atr = sum(trs[:period]) / min(period, len(trs))
        for tr in trs[min(period, len(trs)):]:
            atr = (atr * (period - 1) + tr) / period
        return atr

    def _adx(self, candles: List[Dict], period: int = 14) -> float:
        """Wilder's Average Directional Index."""
        if len(candles) < period * 2:
            return 20.0

        highs  = [float(c["high"])  for c in candles]
        lows   = [float(c["low"])   for c in candles]
        closes = [float(c["close"]) for c in candles]

        dm_plus, dm_minus, tr_list = [], [], []
        for i in range(1, len(candles)):
            up   = highs[i]  - highs[i - 1]
            down = lows[i - 1] - lows[i]
            dm_plus.append(up   if up > down and up > 0   else 0.0)
            dm_minus.append(down if down > up and down > 0 else 0.0)
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i]  - closes[i - 1])
            tr_list.append(max(hl, hc, lc))

        def _wilder_smooth(vals: List[float], p: int) -> List[float]:
            smooth = [sum(vals[:p])]
            for v in vals[p:]:
                smooth.append(smooth[-1] - smooth[-1] / p + v)
            return smooth

        atr_s  = _wilder_smooth(tr_list, period)
        dmp_s  = _wilder_smooth(dm_plus, period)
        dmn_s  = _wilder_smooth(dm_minus, period)

        di_plus  = [100 * d / a if a else 0 for d, a in zip(dmp_s, atr_s)]
        di_minus = [100 * d / a if a else 0 for d, a in zip(dmn_s, atr_s)]

        dx_list = []
        for p, m in zip(di_plus, di_minus):
            denom = p + m
            dx_list.append(100 * abs(p - m) / denom if denom else 0.0)

        if len(dx_list) < period:
            return 20.0

        adx_vals = _wilder_smooth(dx_list, period)
        return round(adx_vals[-1], 1) if adx_vals else 20.0

    def _price_slope(self, candles: List[Dict]) -> float:
        """Linear regression slope of close prices (positive = uptrend)."""
        closes = [float(c["close"]) for c in candles]
        n = len(closes)
        if n < 2:
            return 0.0
        x_mean = (n - 1) / 2
        y_mean = sum(closes) / n
        num = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        return num / den if den else 0.0

    def _range_pct(self, candles: List[Dict]) -> float:
        if not candles:
            return 0.0
        highs  = [float(c["high"]) for c in candles]
        lows   = [float(c["low"])  for c in candles]
        mid    = (max(highs) + min(lows)) / 2
        return (max(highs) - min(lows)) / mid * 100 if mid else 0.0


market_regime_detector = MarketRegimeDetector()
