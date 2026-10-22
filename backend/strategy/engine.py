"""
Gold_AI v2 decision engine.

One function — ``evaluate_bar`` — decides BUY / SELL / NO TRADE for a single
CLOSED primary-timeframe bar. The live endpoint and the backtester both call
it, so what is backtested is exactly what is served.

Strategy (trend-pullback continuation, rules fixed before testing):
  Context  (H4): trend UP  = EMA50 > EMA200, close > EMA50, EMA50 rising
                 trend DOWN = mirror; anything else = no context trend
  Regime   (H1): HIGH/LOW volatility by ATR / median-ATR(100);
                 TREND_UP/DOWN by ADX ≥ 22 and EMA20 vs EMA50;
                 RANGE by ADX < 18; otherwise TRANSITION
  Setup    BUY : regime TREND_UP and context UP; within the last 5 bars price
                 pulled back to EMA20 (low ≤ EMA20 + 0.25·ATR) without closing
                 below EMA50 − 0.25·ATR; trigger bar closes bullish above the
                 previous high and above EMA20; RSI < 70.   SELL = mirror.
  SL           : beyond the 5-bar swing ± 0.2·ATR, widened to ≥ 0.8·ATR,
                 rejected if > 2.5·ATR
  TP           : entry ± target_rr·risk; TP1 at 1R (informational)
  Filters      : opposing swing must leave ≥ min_room_r of room, spread and
                 cost checks, rollover hours, RR after costs ≥ min_rr

``signal_score`` (0-100) is a transparent sum of named components. It is NOT a
win probability — no calibration exists.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from strategy import STRATEGY_VERSION
from strategy import indicators as ind
from strategy.config import RiskConfig, StrategyConfig

BUY, SELL, NO_TRADE = "BUY", "SELL", "NO TRADE"

# Regime labels
TREND_UP, TREND_DOWN = "TREND_UP", "TREND_DOWN"
RANGE, TRANSITION = "RANGE", "TRANSITION"
HIGH_VOL, LOW_VOL = "HIGH_VOLATILITY", "LOW_VOLATILITY"
INSUFFICIENT = "INSUFFICIENT_DATA"


@dataclass
class SignalDecision:
    action: str
    reason_codes: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    regime: str = INSUFFICIENT
    context_trend: str = "NONE"
    bar_open: Optional[str] = None
    bar_close: Optional[str] = None
    entry: Optional[float] = None
    entry_zone: Optional[Dict[str, float]] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    tp1: Optional[float] = None
    risk: Optional[float] = None
    rr: Optional[float] = None
    rr_net: Optional[float] = None
    cost: Optional[float] = None
    signal_score: Optional[float] = None
    score_components: Dict[str, float] = field(default_factory=dict)
    expires_at: Optional[str] = None
    invalidation: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    strategy_version: str = STRATEGY_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Preparation (vectorised, causal) ─────────────────────────────────────────

def prepare_primary(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    p = df.copy().reset_index(drop=True)
    h, l, c = p["high"].to_numpy(), p["low"].to_numpy(), p["close"].to_numpy()
    p["ema_fast"] = ind.ema(c, cfg.ema_fast)
    p["ema_slow"] = ind.ema(c, cfg.ema_slow)
    p["atr"] = ind.atr(h, l, c, cfg.atr_period)
    p["atr_med"] = ind.rolling_median(p["atr"].to_numpy(), cfg.atr_baseline)
    p["adx"] = ind.adx(h, l, c, cfg.adx_period)
    p["rsi"] = ind.rsi(c, cfg.rsi_period)
    p["close_time"] = p["timestamp"] + pd.Timedelta(minutes=cfg.primary_tf)
    return p


def prepare_context(df: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    x = df.copy().reset_index(drop=True)
    c = x["close"].to_numpy()
    x["c_ema_slow"] = ind.ema(c, cfg.ema_slow)
    x["c_ema_trend"] = ind.ema(c, cfg.ema_trend)
    slope = x["c_ema_slow"] - x["c_ema_slow"].shift(5)
    up = (x["c_ema_slow"] > x["c_ema_trend"]) & (x["close"] > x["c_ema_slow"]) & (slope > 0)
    dn = (x["c_ema_slow"] < x["c_ema_trend"]) & (x["close"] < x["c_ema_slow"]) & (slope < 0)
    x["c_trend"] = np.where(up, "UP", np.where(dn, "DOWN", "NONE"))
    x.loc[x["c_ema_trend"].isna(), "c_trend"] = "NONE"
    x["c_close_time"] = x["timestamp"] + pd.Timedelta(minutes=cfg.context_tf)
    return x


def attach_context(primary: pd.DataFrame, context: Optional[pd.DataFrame]) -> pd.DataFrame:
    """For each primary bar, use the latest context bar CLOSED at or before it."""
    p = primary.sort_values("close_time")
    if context is None or context.empty:
        p["c_trend"] = "NONE"
        p["c_close"] = np.nan
        p["c_ema_trend"] = np.nan
        return p.reset_index(drop=True)
    ctx = context[["c_close_time", "c_trend", "close", "c_ema_trend"]].rename(columns={"close": "c_close"})
    merged = pd.merge_asof(p, ctx.sort_values("c_close_time"), left_on="close_time",
                           right_on="c_close_time", direction="backward")
    merged["c_trend"] = merged["c_trend"].fillna("NONE")
    return merged.reset_index(drop=True)


# ── Regime ───────────────────────────────────────────────────────────────────

def classify_regime(row: pd.Series, cfg: StrategyConfig) -> str:
    atr_v, med, adx_v = row["atr"], row["atr_med"], row["adx"]
    if not (np.isfinite(atr_v) and np.isfinite(med) and np.isfinite(adx_v)) or med <= 0:
        return INSUFFICIENT
    ratio = atr_v / med
    if ratio > cfg.vol_high_ratio:
        return HIGH_VOL
    if ratio < cfg.vol_low_ratio:
        return LOW_VOL
    if adx_v >= cfg.adx_trend_min:
        return TREND_UP if row["ema_fast"] > row["ema_slow"] else TREND_DOWN
    if adx_v < cfg.adx_range_max:
        return RANGE
    return TRANSITION


# ── Helpers ──────────────────────────────────────────────────────────────────

def _confirmed_swings(highs: np.ndarray, lows: np.ndarray, end: int, lookback: int, k: int = 2):
    """Fractal swings in [end-lookback, end], each confirmed by k bars on both sides (≤ end)."""
    sh, sl = [], []
    start = max(k, end - lookback)
    for j in range(start, end - k + 1):
        if highs[j] >= highs[j - k:j + k + 1].max():
            sh.append(float(highs[j]))
        if lows[j] <= lows[j - k:j + k + 1].min():
            sl.append(float(lows[j]))
    return sh, sl


def _context_ok(ctx: str, wanted: str, cfg: StrategyConfig) -> bool:
    if cfg.context_mode == "not_against":
        return ctx in (wanted, "NONE")
    return ctx == wanted


def _r(x: Optional[float], nd: int = 2) -> Optional[float]:
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def _no_trade(dec: SignalDecision, code: str, text: str) -> SignalDecision:
    dec.action = NO_TRADE
    dec.reason_codes.append(code)
    dec.reasons.append(text)
    return dec


# ── Core decision ────────────────────────────────────────────────────────────

def evaluate_bar(
    p: pd.DataFrame,
    i: int,
    cfg: StrategyConfig,
    risk_cfg: RiskConfig,
    spread: Optional[float] = None,
) -> SignalDecision:
    """Decide for closed bar ``i`` of a frame produced by prepare_primary+attach_context."""
    spread = risk_cfg.spread if spread is None else float(spread)
    row = p.iloc[i]
    dec = SignalDecision(action=NO_TRADE)
    dec.bar_open = pd.Timestamp(row["timestamp"]).isoformat()
    dec.bar_close = pd.Timestamp(row["close_time"]).isoformat()
    dec.context_trend = str(row.get("c_trend", "NONE"))

    regime = classify_regime(row, cfg)
    dec.regime = regime
    atr_v = float(row["atr"]) if np.isfinite(row["atr"]) else float("nan")
    dec.metrics = {
        "close": _r(row["close"]), "atr": _r(atr_v), "adx": _r(row["adx"], 1),
        "rsi": _r(row["rsi"], 1), "ema_fast": _r(row["ema_fast"]), "ema_slow": _r(row["ema_slow"]),
        "atr_ratio": _r(atr_v / row["atr_med"], 2) if np.isfinite(row["atr_med"]) and row["atr_med"] else None,
        "spread": spread,
    }

    if regime == INSUFFICIENT or i < cfg.pullback_lookback + 2:
        return _no_trade(dec, "INSUFFICIENT_HISTORY", "Indikatorlar uchun tarix yetarli emas")
    if regime == HIGH_VOL:
        return _no_trade(dec, "VOLATILITY_TOO_HIGH", f"ATR odatdagidan {dec.metrics['atr_ratio']}× yuqori — keskin bozor")
    if regime == LOW_VOL:
        return _no_trade(dec, "VOLATILITY_TOO_LOW", f"ATR odatdagidan past ({dec.metrics['atr_ratio']}×) — harakat yo'q")

    close_hour = pd.Timestamp(row["close_time"]).hour
    if cfg.rollover_start_utc <= close_hour < cfg.rollover_end_utc:
        return _no_trade(dec, "ROLLOVER_SESSION", "21:00–23:00 UTC rollover — spread kengayadi")

    if spread > risk_cfg.max_spread:
        return _no_trade(dec, "SPREAD_TOO_HIGH", f"Spread {spread:.2f} > ruxsat {risk_cfg.max_spread:.2f}")

    o = p["open"].to_numpy()
    h = p["high"].to_numpy()
    l = p["low"].to_numpy()
    c = p["close"].to_numpy()
    ef, es = float(row["ema_fast"]), float(row["ema_slow"])
    L = cfg.pullback_lookback
    win = slice(i - L + 1, i + 1)
    ctx = dec.context_trend

    direction = None
    if regime == TREND_UP:
        if not _context_ok(ctx, "UP", cfg):
            return _no_trade(dec, "HTF_CONFLICT", f"H1 trend yuqoriga, lekin H4 konteksti: {ctx}")
        touched = l[win].min() <= ef + cfg.pullback_touch_atr * atr_v
        held = c[win].min() >= es - 0.25 * atr_v
        trigger = c[i] > o[i] and c[i] > h[i - 1] and c[i] > ef
        if not touched:
            return _no_trade(dec, "NO_PULLBACK", "Trend bor, lekin EMA20 ga pullback bo'lmadi (kirish kech)")
        if not held:
            return _no_trade(dec, "PULLBACK_TOO_DEEP", "Pullback EMA50 ostida yopildi — trend zaiflashgan")
        if not trigger:
            return _no_trade(dec, "NO_TRIGGER", "Tasdiqlovchi bullish sham (oldingi high'dan yuqori yopilish) yo'q")
        if row["rsi"] >= cfg.rsi_buy_max:
            return _no_trade(dec, "RSI_OVERBOUGHT", f"RSI {row['rsi']:.0f} — overbought, kirish kech")
        direction = BUY
    elif regime == TREND_DOWN:
        if not _context_ok(ctx, "DOWN", cfg):
            return _no_trade(dec, "HTF_CONFLICT", f"H1 trend pastga, lekin H4 konteksti: {ctx}")
        touched = h[win].max() >= ef - cfg.pullback_touch_atr * atr_v
        held = c[win].max() <= es + 0.25 * atr_v
        trigger = c[i] < o[i] and c[i] < l[i - 1] and c[i] < ef
        if not touched:
            return _no_trade(dec, "NO_PULLBACK", "Trend bor, lekin EMA20 ga pullback bo'lmadi (kirish kech)")
        if not held:
            return _no_trade(dec, "PULLBACK_TOO_DEEP", "Pullback EMA50 ustida yopildi — trend zaiflashgan")
        if not trigger:
            return _no_trade(dec, "NO_TRIGGER", "Tasdiqlovchi bearish sham (oldingi low'dan past yopilish) yo'q")
        if row["rsi"] <= cfg.rsi_sell_min:
            return _no_trade(dec, "RSI_OVERSOLD", f"RSI {row['rsi']:.0f} — oversold, kirish kech")
        direction = SELL
    elif regime == RANGE and cfg.enable_range_setup:
        lo20, hi20 = l[max(0, i - 19):i + 1].min(), h[max(0, i - 19):i + 1].max()
        if l[i] <= lo20 + 0.25 * atr_v and c[i] > o[i] and row["rsi"] <= cfg.range_rsi_buy and ctx != "DOWN":
            direction = BUY
        elif h[i] >= hi20 - 0.25 * atr_v and c[i] < o[i] and row["rsi"] >= cfg.range_rsi_sell and ctx != "UP":
            direction = SELL
        else:
            return _no_trade(dec, "RANGE_NO_EDGE", "Range: narx chegarada emas yoki tasdiq yo'q")
    elif regime == RANGE:
        return _no_trade(dec, "RANGE_DISABLED", "Range rejimi — tasdiqlangan strategiya yo'q")
    else:
        return _no_trade(dec, "TRANSITION", f"ADX {row['adx']:.0f} — trend ham, range ham aniq emas")

    # ── SL / TP construction ────────────────────────────────────────────────
    entry = float(c[i])
    sw = slice(i - cfg.sl_swing_lookback + 1, i + 1)
    if direction == BUY:
        sl = float(l[sw].min()) - cfg.sl_buffer_atr * atr_v
        risk = entry - sl
    else:
        sl = float(h[sw].max()) + cfg.sl_buffer_atr * atr_v
        risk = sl - entry
    if risk < cfg.sl_min_atr * atr_v:
        risk = cfg.sl_min_atr * atr_v
        sl = entry - risk if direction == BUY else entry + risk
    if risk > cfg.sl_max_atr * atr_v:
        return _no_trade(dec, "SL_TOO_WIDE", f"SL masofasi {risk:.2f} > {cfg.sl_max_atr}×ATR")
    if risk <= 0 or not np.isfinite(risk):
        return _no_trade(dec, "INVALID_SL", "SL hisoblab bo'lmadi")

    sign = 1 if direction == BUY else -1
    tp = entry + sign * cfg.target_rr * risk
    tp1 = entry + sign * cfg.tp1_rr * risk
    cost = spread + 2 * risk_cfg.slippage
    rr = (abs(tp - entry)) / risk
    rr_net = (abs(tp - entry) - cost) / (risk + cost)

    if spread / risk > risk_cfg.max_spread_to_risk:
        return _no_trade(dec, "SPREAD_TOO_HIGH_VS_SL", f"Spread SL masofasining {spread / risk:.0%} qismi")
    if rr_net < cfg.min_rr:
        return _no_trade(dec, "RR_TOO_LOW", f"Xarajatlardan keyingi RR {rr_net:.2f} < {cfg.min_rr}")

    # room to the opposing confirmed swing
    sh, sl_sw = _confirmed_swings(h, l, i, cfg.room_swing_lookback)
    if direction == BUY:
        blockers = [x for x in sh if x > entry]
        room = (min(blockers) - entry) if blockers else None
    else:
        blockers = [x for x in sl_sw if x < entry]
        room = (entry - max(blockers)) if blockers else None
    room_r = room / risk if room is not None else None
    if cfg.min_room_r > 0 and room_r is not None and room_r < cfg.min_room_r:
        return _no_trade(dec, "NO_ROOM_TO_TARGET",
                         f"Qarshi swing darajasi atigi {room_r:.2f}R uzoqlikda")

    # ── Score (informational, not a probability) ────────────────────────────
    comps: Dict[str, float] = {}
    c_close, c_ema_t = row.get("c_close"), row.get("c_ema_trend")
    strong_ctx = (np.isfinite(c_close) and np.isfinite(c_ema_t)
                  and ((direction == BUY and c_close > c_ema_t) or (direction == SELL and c_close < c_ema_t)))
    comps["htf_alignment"] = 25.0 if strong_ctx else (15.0 if ctx in ("UP", "DOWN") else 5.0)
    comps["trend_strength"] = round(20.0 * float(np.clip((row["adx"] - cfg.adx_trend_min) / 18.0, 0, 1)), 1)
    depth = ((ef - l[win].min()) if direction == BUY else (h[win].max() - ef)) / atr_v
    comps["pullback_quality"] = 20.0 if -cfg.pullback_touch_atr <= depth <= 1.0 else 10.0
    rng = h[i] - l[i]
    comps["trigger_strength"] = round(15.0 * (abs(c[i] - o[i]) / rng if rng > 0 else 0.0), 1)
    comps["room_to_target"] = 10.0 if room_r is None else round(10.0 * min(room_r / cfg.target_rr, 1.0), 1)
    ratio = dec.metrics["atr_ratio"] or 1.0
    comps["volatility_normal"] = 10.0 if 0.7 <= ratio <= 1.5 else 5.0
    score = round(sum(comps.values()), 1)
    if score < cfg.min_signal_score:
        return _no_trade(dec, "SCORE_BELOW_MIN", f"Signal score {score} < {cfg.min_signal_score}")

    # ── Fill decision ───────────────────────────────────────────────────────
    zone = cfg.entry_zone_atr * atr_v
    bar_close = pd.Timestamp(row["close_time"]).to_pydatetime()
    dec.action = direction
    dec.entry = _r(entry)
    dec.entry_zone = {"low": _r(entry - zone if direction == BUY else entry - 0.1 * atr_v),
                      "high": _r(entry + 0.1 * atr_v if direction == BUY else entry + zone)}
    dec.stop_loss, dec.take_profit, dec.tp1 = _r(sl), _r(tp), _r(tp1)
    dec.risk, dec.rr, dec.rr_net, dec.cost = _r(risk), _r(rr), _r(rr_net), _r(cost)
    dec.signal_score, dec.score_components = score, comps
    dec.expires_at = (bar_close + timedelta(minutes=cfg.primary_tf * cfg.expiry_bars)).isoformat()
    side_word = "ostida" if direction == BUY else "ustida"
    dec.invalidation = [
        f"Kirishdan oldin narx {dec.stop_loss} {side_word} bo'lsa — bekor",
        f"Narx kirish zonasidan ({dec.entry_zone['low']}–{dec.entry_zone['high']}) chiqib ketsa — quvmang",
        f"{dec.expires_at} UTC dan keyin kirilmagan bo'lsa — eskirgan",
        "Yuqori ta'sirli USD yangiligi ±30 daqiqa ichida bo'lsa — kirmang",
    ]
    trend_word = "yuqoriga" if direction == BUY else "pastga"
    dec.reasons = [
        f"H4 konteksti {ctx}, H1 rejimi {regime} (ADX {row['adx']:.0f})",
        f"EMA20 ga pullback va tasdiqlovchi sham — trend {trend_word} davom etish setupi",
        f"SL struktura ortida ({risk:.2f} = {risk / atr_v:.1f}×ATR), TP {cfg.target_rr}R",
        f"Xarajatlar (spread+slippage) {cost:.2f} → RR net {rr_net:.2f}",
    ]
    dec.reason_codes = ["TREND_PULLBACK"] if regime in (TREND_UP, TREND_DOWN) else ["RANGE_REVERSION"]
    dec.metrics["room_r"] = _r(room_r)
    return dec
