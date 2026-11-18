"""
Owner notifications on Telegram that the signal alert path does not cover:
paper-trade lifecycle events and a daily digest. Messages use legacy Markdown
(``telegram_service.broadcast``); dynamic text goes through ``watchdog.md``.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

from services.watchdog import md

log = logging.getLogger(__name__)

EXIT_TEXT = {
    "TP": "🎯 Take Profit", "SL": "🛑 Stop Loss", "SL_GAP": "🛑 Stop Loss (narx sakradi)",
    "SL_AMBIGUOUS": "🛑 Stop Loss (bir shamda SL va TP)", "TIME": "⏱ Vaqt bo'yicha yopildi",
    "EXPIRED": "muddat tugadi", "ENTRY_ZONE_MISSED": "narx kirish zonasidan tashqarida ochildi",
    "OPENED_BEYOND_LEVELS": "narx SL/TP dan o'tib ochildi",
}


def _f(v: Optional[float], d: int = 2) -> str:
    return "—" if v is None else f"{v:,.{d}f}"


def paper_event_messages(changes: Iterable[Dict[str, Any]]) -> List[str]:
    """One message per paper trade whose status changed in this tick."""
    out = []
    for c in changes:
        prev, now = c.get("prev_status"), c.get("status")
        if prev == now:
            continue
        side = c.get("direction", "")
        head = f"🧪 *Paper #{c.get('id')}* {side}"
        if now == "OPEN":
            out.append(f"{head} — *kirildi* @ {_f(c.get('fill_price'))}\n"
                       f"SL {_f(c.get('stop_loss'))} · TP {_f(c.get('take_profit'))} · {_f(c.get('lots'))} lot")
        elif now == "CLOSED":
            r, pnl = c.get("r"), c.get("pnl_usd")
            sign = "+" if (pnl or 0) > 0 else ""
            out.append(f"{head} — {EXIT_TEXT.get(c.get('exit_reason'), md(c.get('exit_reason')))}\n"
                       f"Kirish {_f(c.get('fill_price'))} → chiqish {_f(c.get('exit_price'))}\n"
                       f"Natija: *{sign}{_f(r)}R* ({sign}${_f(pnl)})")
        elif now == "CANCELLED":
            out.append(f"{head} — kirilmadi: {EXIT_TEXT.get(c.get('exit_reason'), md(c.get('exit_reason')))}")
    return out


def notify_paper_changes(result: Dict[str, Any], send: Optional[Callable[[str], Any]] = None) -> int:
    if send is None:
        from services.telegram_service import broadcast as send
    msgs = paper_event_messages(result.get("trades") or [])
    for m in msgs:
        try:
            send(m)
        except Exception:
            log.exception("Paper notification failed")
    return len(msgs)


def daily_summary_text(db, now: Optional[datetime] = None) -> str:
    from models.signal import Signal
    from paper import service as paper
    from services import watchdog
    from services.signal_outcomes import performance
    from services.twelvedata_service import get_price

    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    day_start = now - timedelta(hours=24)
    rows = db.query(Signal).filter(Signal.created_at >= day_start).all()
    trades = [s for s in rows if s.signal_type in ("BUY", "SELL")]
    reasons: Dict[str, int] = {}
    for s in rows:
        if s.signal_type == "NO TRADE" and s.reasoning:
            key = s.reasoning.split("|")[0].strip()[:40]
            reasons[key] = reasons.get(key, 0) + 1
    top = sorted(reasons.items(), key=lambda kv: -kv[1])[:3]

    tick = get_price("XAUUSD") or {}
    st = paper.stats(db)
    acc = st["account"]
    perf = performance(db, symbol="XAUUSD", days=30)["overall"]
    wd = watchdog.status()

    lines = [f"📊 *Gold AI — kunlik hisobot* ({now:%Y-%m-%d} UTC)",
             f"XAUUSD: {_f(tick.get('price'))}",
             "",
             f"*Signallar (24 soat):* {len(rows)} ta tahlil, {len(trades)} ta BUY/SELL"]
    for s in trades:
        lines.append(f"  • {s.signal_type} @ {_f(s.entry)} (SL {_f(s.stop_loss)}, TP {_f(s.take_profit)})")
    if top:
        lines.append("NO TRADE sabablari: " + ", ".join(f"{md(k)} ×{v}" for k, v in top))
    lines += ["",
              f"*Paper hisob:* ${_f(acc['balance'])} (boshlang'ich ${_f(acc['start_balance'], 0)})",
              f"Yopilgan: {st['trades']} · ochiq/kutilayotgan: {st['open_or_pending']}"
              + (" · ⛔️ TO'XTATILGAN" if acc.get("halted") else "")]
    if perf.get("trades"):
        lines.append(f"Signal natijalari (30 kun): {perf['trades']} ta, win {_f(perf.get('win_rate'), 0)}%, "
                     f"o'rtacha {_f(perf.get('expectancy_r'))}R")
    bad = [k for k, v in wd["checks"].items() if not v.get("ok", True)]
    lines += ["", "Tizim: " + ("✅ hammasi ishlayapti" if not bad else "⚠️ muammo: " + ", ".join(watchdog.LABEL.get(b, b) for b in bad))]
    return "\n".join(lines)
