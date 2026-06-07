"""
Full technical indicator suite for GOLD AI.
All calculations are pure-Python with no external TA library dependency,
enabling reliable operation in CI and non-Windows environments.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


class IndicatorCalculator:
    """Stateless calculator — every method takes a list of OHLCV dicts."""

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _closes(candles: List[Dict[str, Any]]) -> List[float]:
        return [float(c["close"]) for c in candles]

    @staticmethod
    def _highs(candles: List[Dict[str, Any]]) -> List[float]:
        return [float(c["high"]) for c in candles]

    @staticmethod
    def _lows(candles: List[Dict[str, Any]]) -> List[float]:
        return [float(c["low"]) for c in candles]

    @staticmethod
    def _volumes(candles: List[Dict[str, Any]]) -> List[float]:
        return [float(c.get("volume") or 0.0) for c in candles]

    @staticmethod
    def _ema(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        sma = sum(values[:period]) / period
        k = 2.0 / (period + 1)
        ema = sma
        for v in values[period:]:
            ema = v * k + ema * (1 - k)
        return ema

    @staticmethod
    def _sma(values: List[float], period: int) -> Optional[float]:
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    @staticmethod
    def _stdev(values: List[float]) -> float:
        n = len(values)
        if n < 2:
            return 0.0
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / n
        return math.sqrt(variance)

    # ------------------------------------------------------------------ EMAs
    def ema(self, candles: List[Dict[str, Any]], period: int) -> Optional[float]:
        return self._ema(self._closes(candles), period)

    def ema20(self, candles: List[Dict[str, Any]]) -> Optional[float]:
        return self.ema(candles, 20)

    def ema50(self, candles: List[Dict[str, Any]]) -> Optional[float]:
        return self.ema(candles, 50)

    def ema100(self, candles: List[Dict[str, Any]]) -> Optional[float]:
        return self.ema(candles, 100)

    def ema200(self, candles: List[Dict[str, Any]]) -> Optional[float]:
        return self.ema(candles, 200)

    # ------------------------------------------------------------------ RSI
    def rsi(self, candles: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
        closes = self._closes(candles)
        if len(closes) <= period:
            return None
        gains = losses = 0.0
        for i in range(1, period + 1):
            delta = closes[i] - closes[i - 1]
            if delta > 0:
                gains += delta
            else:
                losses += -delta
        avg_gain = gains / period
        avg_loss = losses / period
        for i in range(period + 1, len(closes)):
            delta = closes[i] - closes[i - 1]
            g = max(delta, 0.0)
            l = max(-delta, 0.0)
            avg_gain = (avg_gain * (period - 1) + g) / period
            avg_loss = (avg_loss * (period - 1) + l) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    # ------------------------------------------------------------------ MACD
    def macd(
        self,
        candles: List[Dict[str, Any]],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> Dict[str, Optional[float]]:
        closes = self._closes(candles)
        if len(closes) < slow + signal:
            return {"macd": None, "signal": None, "histogram": None}
        macd_series: List[float] = []
        for i in range(slow - 1, len(closes)):
            window = closes[: i + 1]
            fast_ema = self._ema(window, fast)
            slow_ema = self._ema(window, slow)
            if fast_ema is not None and slow_ema is not None:
                macd_series.append(fast_ema - slow_ema)
        if len(macd_series) < signal:
            return {"macd": None, "signal": None, "histogram": None}
        signal_line = self._ema(macd_series, signal)
        macd_val = macd_series[-1]
        hist = (macd_val - signal_line) if signal_line is not None else None
        return {"macd": macd_val, "signal": signal_line, "histogram": hist}

    # ------------------------------------------------------------------ Stochastic
    def stochastic(
        self,
        candles: List[Dict[str, Any]],
        k_period: int = 14,
        d_period: int = 3,
    ) -> Dict[str, Optional[float]]:
        if len(candles) < k_period + d_period:
            return {"k": None, "d": None}
        highs = self._highs(candles)
        lows = self._lows(candles)
        closes = self._closes(candles)
        k_values: List[float] = []
        for i in range(k_period - 1, len(candles)):
            h = max(highs[i - k_period + 1 : i + 1])
            l = min(lows[i - k_period + 1 : i + 1])
            if h == l:
                k_values.append(50.0)
            else:
                k_values.append(100.0 * (closes[i] - l) / (h - l))
        if not k_values:
            return {"k": None, "d": None}
        k = k_values[-1]
        d = self._sma(k_values, d_period) if len(k_values) >= d_period else None
        return {"k": k, "d": d}

    # ------------------------------------------------------------------ ATR
    def atr(self, candles: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
        if len(candles) < period + 1:
            return None
        highs = self._highs(candles)
        lows = self._lows(candles)
        closes = self._closes(candles)
        trs: List[float] = []
        for i in range(1, len(candles)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            trs.append(max(hl, hc, lc))
        if len(trs) < period:
            return None
        # Wilder's smoothing
        atr_val = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr_val = (atr_val * (period - 1) + tr) / period
        return atr_val

    # ------------------------------------------------------------------ Bollinger Bands
    def bollinger_bands(
        self,
        candles: List[Dict[str, Any]],
        period: int = 20,
        multiplier: float = 2.0,
    ) -> Dict[str, Optional[float]]:
        closes = self._closes(candles)
        if len(closes) < period:
            return {"upper": None, "middle": None, "lower": None, "bandwidth": None}
        window = closes[-period:]
        middle = sum(window) / period
        std = self._stdev(window)
        upper = middle + multiplier * std
        lower = middle - multiplier * std
        bandwidth = (upper - lower) / middle if middle != 0 else None
        return {"upper": upper, "middle": middle, "lower": lower, "bandwidth": bandwidth}

    # ------------------------------------------------------------------ VWAP
    def vwap(self, candles: List[Dict[str, Any]]) -> Optional[float]:
        """Session VWAP using all provided candles."""
        volumes = self._volumes(candles)
        total_vol = sum(volumes)
        if total_vol == 0:
            return None
        typical_prices = [
            (float(c["high"]) + float(c["low"]) + float(c["close"])) / 3.0
            for c in candles
        ]
        return sum(tp * v for tp, v in zip(typical_prices, volumes)) / total_vol

    # ------------------------------------------------------------------ OBV
    def obv(self, candles: List[Dict[str, Any]]) -> Optional[float]:
        closes = self._closes(candles)
        volumes = self._volumes(candles)
        if len(closes) < 2:
            return None
        obv_val = volumes[0]
        for i in range(1, len(closes)):
            if closes[i] > closes[i - 1]:
                obv_val += volumes[i]
            elif closes[i] < closes[i - 1]:
                obv_val -= volumes[i]
        return obv_val

    # ------------------------------------------------------------------ ADX
    def adx(self, candles: List[Dict[str, Any]], period: int = 14) -> Dict[str, Optional[float]]:
        if len(candles) < period * 2:
            return {"adx": None, "plus_di": None, "minus_di": None}
        highs = self._highs(candles)
        lows = self._lows(candles)
        closes = self._closes(candles)

        trs: List[float] = []
        plus_dms: List[float] = []
        minus_dms: List[float] = []

        for i in range(1, len(candles)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            trs.append(max(hl, hc, lc))

            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
            minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0
            plus_dms.append(plus_dm)
            minus_dms.append(minus_dm)

        if len(trs) < period:
            return {"adx": None, "plus_di": None, "minus_di": None}

        # Wilder's smoothing
        smooth_tr = sum(trs[:period])
        smooth_plus = sum(plus_dms[:period])
        smooth_minus = sum(minus_dms[:period])

        dx_series: List[float] = []
        for i in range(period, len(trs)):
            smooth_tr = smooth_tr - smooth_tr / period + trs[i]
            smooth_plus = smooth_plus - smooth_plus / period + plus_dms[i]
            smooth_minus = smooth_minus - smooth_minus / period + minus_dms[i]

        plus_di = 100 * smooth_plus / smooth_tr if smooth_tr else 0.0
        minus_di = 100 * smooth_minus / smooth_tr if smooth_tr else 0.0

        # Build DX series for ADX
        smooth_tr2 = sum(trs[:period])
        smooth_plus2 = sum(plus_dms[:period])
        smooth_minus2 = sum(minus_dms[:period])
        for i in range(period, len(trs)):
            smooth_tr2 = smooth_tr2 - smooth_tr2 / period + trs[i]
            smooth_plus2 = smooth_plus2 - smooth_plus2 / period + plus_dms[i]
            smooth_minus2 = smooth_minus2 - smooth_minus2 / period + minus_dms[i]
            pdi = 100 * smooth_plus2 / smooth_tr2 if smooth_tr2 else 0.0
            mdi = 100 * smooth_minus2 / smooth_tr2 if smooth_tr2 else 0.0
            denom = pdi + mdi
            dx = 100 * abs(pdi - mdi) / denom if denom else 0.0
            dx_series.append(dx)

        if len(dx_series) < period:
            return {"adx": None, "plus_di": plus_di, "minus_di": minus_di}

        adx_val = sum(dx_series[:period]) / period
        for dx in dx_series[period:]:
            adx_val = (adx_val * (period - 1) + dx) / period

        return {"adx": adx_val, "plus_di": plus_di, "minus_di": minus_di}

    # ------------------------------------------------------------------ compute all
    def compute_all(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Return a flat dict of all indicator values for the latest candle."""
        result: Dict[str, Any] = {}

        result["EMA_20"] = self.ema20(candles)
        result["EMA_50"] = self.ema50(candles)
        result["EMA_100"] = self.ema100(candles)
        result["EMA_200"] = self.ema200(candles)

        result["RSI_14"] = self.rsi(candles, 14)

        macd_data = self.macd(candles)
        result["MACD_line"] = macd_data["macd"]
        result["MACD_signal"] = macd_data["signal"]
        result["MACD_hist"] = macd_data["histogram"]

        stoch = self.stochastic(candles)
        result["STOCH_K"] = stoch["k"]
        result["STOCH_D"] = stoch["d"]

        result["ATR_14"] = self.atr(candles, 14)

        bb = self.bollinger_bands(candles)
        result["BB_upper"] = bb["upper"]
        result["BB_middle"] = bb["middle"]
        result["BB_lower"] = bb["lower"]
        result["BB_bandwidth"] = bb["bandwidth"]

        result["VWAP"] = self.vwap(candles)
        result["OBV"] = self.obv(candles)

        adx_data = self.adx(candles)
        result["ADX"] = adx_data["adx"]
        result["PLUS_DI"] = adx_data["plus_di"]
        result["MINUS_DI"] = adx_data["minus_di"]

        return result


calculator = IndicatorCalculator()
