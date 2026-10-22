"""
Live signal generation: data checks → decision → risk sizing → audit log.

Pure with respect to the database: callers pass candles, events and price.
Never places, modifies or closes orders.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from strategy import STRATEGY_VERSION
from strategy.config import RiskConfig, StrategyConfig
from strategy.data_quality import OK, assess, clean_candles
from strategy.engine import BUY, NO_TRADE, SELL, SignalDecision, attach_context, evaluate_bar, \
    prepare_context, prepare_primary

log = logging.getLogger(__name__)
_audit_lock = threading.Lock()

TF_NAMES = {1: "M1", 5: "M5", 15: "M15", 30: "M30", 60: "H1", 240: "H4", 1440: "D1"}

RISK_WARNING = (
    "Bu savdo tavsiyasi emas. Signal score — ehtimollik emas. Strategiya tarixiy "
    "test qilingan, lekin statistik ishonch past (kam savdo). Faqat demo yoki "
    "kichik risk bilan, o'z qaroringiz asosida foydalaning."
)


def _resample_daily(h4: pd.DataFrame) -> pd.DataFrame:
    x = h4.set_index("timestamp")
    d = x.resample("1440min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return d.reset_index()


def position_size(balance: float, risk_per_unit: float, risk: RiskConfig) -> Dict[str, Any]:
    """Lots so that SL loss ≈ balance·risk_pct. Rounded DOWN to lot_step; never inflated."""
    if balance <= 0 or risk_per_unit <= 0:
        return {"lots": None, "risk_amount": 0.0, "note": "Balans yoki SL masofasi noto'g'ri"}
    risk_amount = balance * risk.risk_pct / 100.0
    loss_per_lot = risk_per_unit * risk.contract_size + risk.commission_per_lot
    raw = risk_amount / loss_per_lot
    steps = int(raw / risk.lot_step + 1e-9)
    lots = round(steps * risk.lot_step, 4)
    if lots < risk.min_lot:
        return {"lots": None, "risk_amount": round(risk_amount, 2), "raw_lots": round(raw, 4),
                "note": f"Hisoblangan hajm {raw:.4f} < minimal lot {risk.min_lot} — bu balans bilan risk limiti oshadi"}
    lots = min(lots, risk.max_lot)
    return {"lots": lots, "risk_amount": round(lots * loss_per_lot, 2), "raw_lots": round(raw, 4),
            "note": "contract_size/lot_step broker spetsifikatsiyasi bilan tekshirilishi shart"}


def _news_blackout(events: Iterable[Dict[str, Any]], now: datetime, minutes: int) -> Optional[Dict[str, Any]]:
    for ev in events or []:
        t = ev.get("event_time")
        if t is None or int(ev.get("impact") or 0) < 3:
            continue
        if (ev.get("currency") or "USD").upper() != "USD":
            continue
        if t.tzinfo is not None:
            t = t.astimezone(timezone.utc).replace(tzinfo=None)
        if abs((t - now).total_seconds()) <= minutes * 60:
            return {"event": ev.get("event"), "event_time": t.isoformat()}
    return None


def generate(
    primary_candles: Iterable[Any],
    context_candles: Optional[Iterable[Any]] = None,
    *,
    symbol: str = "XAUUSD",
    now: Optional[datetime] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    live_price: Optional[float] = None,
    live_price_source: Optional[str] = None,
    spread: Optional[float] = None,
    account_balance: float = 10000.0,
    cfg: Optional[StrategyConfig] = None,
    risk: Optional[RiskConfig] = None,
) -> Dict[str, Any]:
    cfg = cfg or StrategyConfig()
    risk = risk or RiskConfig()
    now = (now or datetime.now(timezone.utc))
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)
    spread_source = "broker_quote" if spread is not None else "config_assumption"
    spread = risk.spread if spread is None else float(spread)

    p_df, p_rep = clean_candles(primary_candles, cfg.primary_tf, now)
    assess(p_rep, now, cfg.min_history_bars, cfg.max_stale_bars, cfg.max_gap_bars_in_window)

    # Context: resample the primary series when it is long enough (as in research),
    # otherwise fall back to the stored context candles.
    c_df, c_rep, c_source = pd.DataFrame(), None, None
    if cfg.context_tf == 1440 and cfg.primary_tf == 240 and len(p_df) >= (cfg.ema_trend + 10) * 6:
        c_df, c_rep = clean_candles(_resample_daily(p_df), 1440, now)
        c_source = "resampled_primary"
    elif context_candles is not None:
        c_df, c_rep = clean_candles(context_candles, cfg.context_tf, now)
        c_source = "stored"
    if c_rep is not None:
        # context needs EMA200 history; staleness is judged on the primary TF only
        if c_rep.rows_out < cfg.ema_trend + 10:
            c_rep.status = "INSUFFICIENT_DATA"
            c_rep.issues.append(f"HISTORY_{c_rep.rows_out}_LT_{cfg.ema_trend + 10}")

    base = {
        "instrument": symbol,
        "generated_at": now.isoformat() + "Z",
        "timezone": "UTC",
        "strategy_version": STRATEGY_VERSION,
        "config_hash": cfg.version_hash(),
        "timeframes": {"primary": TF_NAMES.get(cfg.primary_tf, str(cfg.primary_tf)),
                       "context": TF_NAMES.get(cfg.context_tf, str(cfg.context_tf))},
        "data_status": {"primary": p_rep.to_dict(), "context": c_rep.to_dict() if c_rep else None,
                        "context_source": c_source},
        "spread": {"value": spread, "source": spread_source},
        "live_price": {"value": live_price, "source": live_price_source},
        "risk_warning": RISK_WARNING,
    }

    def _blocked(code: str, text: str) -> Dict[str, Any]:
        dec = SignalDecision(action=NO_TRADE, reason_codes=[code], reasons=[text])
        return _finish(base, dec, account_balance, risk)

    if p_rep.status != OK:
        return _blocked(f"DATA_{p_rep.status}", f"{base['timeframes']['primary']} ma'lumotlari: {p_rep.status} {p_rep.issues}")
    if c_rep is None or c_rep.status != OK:
        st = c_rep.status if c_rep else "MISSING"
        return _blocked(f"CONTEXT_{st}", f"{base['timeframes']['context']} kontekst ma'lumotlari: {st}")

    blackout = _news_blackout(events or [], now, cfg.news_blackout_minutes)
    if blackout:
        base["news_blackout"] = blackout
        return _blocked("NEWS_BLACKOUT", f"Yuqori ta'sirli yangilik: {blackout['event']} ({blackout['event_time']} UTC)")

    p = attach_context(prepare_primary(p_df, cfg), prepare_context(c_df, cfg))
    dec = evaluate_bar(p, len(p) - 1, cfg, risk, spread=spread)

    if dec.action in (BUY, SELL):
        if dec.expires_at and now > datetime.fromisoformat(dec.expires_at):
            dec.action = NO_TRADE
            dec.reason_codes = ["SIGNAL_EXPIRED"] + dec.reason_codes
            dec.reasons.insert(0, "Setup eskirgan — amal qilish muddati o'tgan")
        elif live_price is not None and dec.entry_zone:
            z = dec.entry_zone
            if not (z["low"] <= live_price <= z["high"]):
                dec.action = NO_TRADE
                dec.reason_codes = ["PRICE_LEFT_ENTRY_ZONE"] + dec.reason_codes
                dec.reasons.insert(0, f"Joriy narx {live_price:.2f} kirish zonasidan tashqarida — quvmang")
            elif (dec.action == BUY and live_price <= dec.stop_loss) or (dec.action == SELL and live_price >= dec.stop_loss):
                dec.action = NO_TRADE
                dec.reason_codes = ["SL_ALREADY_HIT"] + dec.reason_codes
        elif live_price is None:
            dec.reasons.append("Diqqat: jonli narx mavjud emas — kirishdan oldin narx zonada ekanini tekshiring")
    return _finish(base, dec, account_balance, risk)


def _finish(base: Dict[str, Any], dec: SignalDecision, balance: float, risk: RiskConfig) -> Dict[str, Any]:
    out = dict(base)
    out.update({
        "direction": dec.action,
        "decision": dec.to_dict(),
        "market_regime": dec.regime,
        "context_trend": dec.context_trend,
        "entry": dec.entry, "entry_zone": dec.entry_zone,
        "stop_loss": dec.stop_loss, "take_profit": dec.take_profit, "tp1": dec.tp1,
        "risk_reward": dec.rr, "risk_reward_net": dec.rr_net,
        "signal_score": dec.signal_score, "score_components": dec.score_components,
        "score_note": "Signal score — qoidalar bajarilish sifati, yutish ehtimoli EMAS",
        "reasons": dec.reasons, "reason_codes": dec.reason_codes,
        "invalidation": dec.invalidation, "expires_at": dec.expires_at,
        "timeframe_confirmation": {
            out["timeframes"]["context"]: dec.context_trend,
            out["timeframes"]["primary"]: dec.regime,
        },
    })
    if dec.action in (BUY, SELL) and dec.risk:
        out["position"] = position_size(balance, dec.risk + (dec.cost or 0) / 2, risk)
        out["position"]["account_balance"] = balance
        out["position"]["risk_pct"] = risk.risk_pct
    else:
        out["position"] = None
    audit(out)
    return out


def audit(payload: Dict[str, Any]) -> None:
    """Append one JSON line per decision. No secrets are present in the payload."""
    path = os.getenv("SIGNAL_AUDIT_LOG") or os.path.join(
        os.getenv("ML_MODEL_DIR", "/app/ml_models"), "signal_audit.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _audit_lock, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str, ensure_ascii=False) + "\n")
    except OSError as exc:  # never fail a signal because the audit log is unavailable
        log.warning("Signal audit log write failed (%s): %s", path, exc)


def legacy_view(sig: Dict[str, Any]) -> Dict[str, Any]:
    """Fields expected by the existing frontend/Telegram/DB schema."""
    d = sig["decision"]
    action = sig["direction"]
    pos = sig.get("position") or {}
    entry, sl, tp = sig["entry"], sig["stop_loss"], sig["take_profit"]

    def pct(x):
        return round(abs(x - entry) / entry * 100, 3) if (x is not None and entry) else None

    reasons = " | ".join(sig["reasons"][:6]) if sig["reasons"] else None
    return {
        "symbol": sig["instrument"],
        "timeframe": str(StrategyConfig().primary_tf),
        "signal_type": action,
        "entry": entry if action != NO_TRADE else None,
        "stop_loss": sl if action != NO_TRADE else None,
        "take_profit": tp if action != NO_TRADE else None,
        "tp1": sig["tp1"] if action != NO_TRADE else None,
        "tp3": None,
        "rr": sig["risk_reward"] if action != NO_TRADE else None,
        # kept for UI compatibility: this is the signal SCORE, not a probability
        "confidence": sig["signal_score"] if action != NO_TRADE else 0.0,
        "technical_score": None, "smc_score": None, "ml_score": None,
        "news_score": None, "economic_score": None,
        "reasoning": reasons,
        "lot_size": pos.get("lots"),
        "risk_amount_usd": pos.get("risk_amount"),
        "sl_distance_pct": pct(sl) if action != NO_TRADE else None,
        "tp1_distance_pct": pct(sig["tp1"]) if action != NO_TRADE else None,
        "tp2_distance_pct": pct(tp) if action != NO_TRADE else None,
        "tp3_distance_pct": None,
        "signal_emoji": "🟢" if action == BUY else "🔴" if action == SELL else "⚪",
        "plain_explanation": plain_text(sig),
        "bar_close": d.get("bar_close"),
    }


def plain_text(sig: Dict[str, Any]) -> str:
    action = sig["direction"]
    tfp, tfc = sig["timeframes"]["primary"], sig["timeframes"]["context"]
    if action == NO_TRADE:
        why = "; ".join(sig["reasons"][:2]) or ", ".join(sig["reason_codes"])
        return (f"⚪ NO TRADE — {sig['instrument']} {tfp}\n"
                f"   Sabab: {why}\n"
                f"   Kodlar: {', '.join(sig['reason_codes'])}\n"
                f"   Rejim: {sig['market_regime']} | {tfc} kontekst: {sig['context_trend']}")
    pos = sig.get("position") or {}
    lots = pos.get("lots")
    z = sig["entry_zone"] or {}
    emoji = "🟢" if action == BUY else "🔴"
    lines = [
        f"{emoji} {action} {sig['instrument']} — {tfp} (kontekst {tfc})",
        f"   Vaqt: {sig['decision']['bar_close']} UTC (yopilgan sham)",
        f"   Kirish: {sig['entry']:.2f}  (zona {z.get('low')}–{z.get('high')})",
        f"   Stop Loss: {sig['stop_loss']:.2f}",
        f"   TP1 (1R, qisman): {sig['tp1']:.2f}",
        f"   Take Profit: {sig['take_profit']:.2f}",
        f"   R/R: {sig['risk_reward']} (xarajatlardan keyin {sig['risk_reward_net']})",
        f"   Signal score: {sig['signal_score']}/100 (ehtimollik emas)",
        f"   Rejim: {sig['market_regime']} | {tfc}: {sig['context_trend']}",
        f"   Spread: {sig['spread']['value']} ({sig['spread']['source']})",
        f"   Lot: {lots if lots is not None else '—'} ({pos.get('note', '')})",
        f"   Amal qilish muddati: {sig['expires_at']} UTC gacha",
        "   Bekor bo'lish shartlari:",
    ] + [f"     • {x}" for x in sig["invalidation"]] + [
        "   Sabablar:",
    ] + [f"     • {x}" for x in sig["reasons"]] + [f"   ⚠️ {sig['risk_warning']}"]
    return "\n".join(lines)
