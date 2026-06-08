"""
Telegram bot service — long-polling, inline keyboard buttons, alert filtering.
Starts in a background thread on app startup.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import httpx

log = logging.getLogger(__name__)


class AlertFilter:
    """
    Prevents signal spam by enforcing confidence thresholds and cooldown windows.

    Rules (evaluated in order):
      1. NO TRADE signals are never sent.
      2. Signals below MIN_CONFIDENCE are skipped.
      3. Same-direction alerts within COOLDOWN_MINUTES are suppressed.
         Direction-reversal alerts require DIRECTION_CHANGE_COOLDOWN minutes.
      4. Re-alerts on the same direction are only sent if confidence improved
         by more than 15 points within COOLDOWN_MINUTES * 2.
    """

    MIN_CONFIDENCE:            float = 65.0
    COOLDOWN_MINUTES:          float = 30.0
    DIRECTION_CHANGE_COOLDOWN: float = 5.0

    def __init__(self) -> None:
        self._last_signal:  Dict[str, Any]     = {}
        self._last_sent_at: Dict[str, datetime] = {}

    def should_send(self, signal: Dict[str, Any]) -> tuple[bool, str]:
        symbol     = signal.get("symbol", "XAUUSD")
        sig_type   = signal.get("signal_type")
        confidence = float(signal.get("confidence") or 0)

        if sig_type == "NO TRADE":
            return False, "no_trade"

        if confidence < self.MIN_CONFIDENCE:
            return False, f"low_confidence_{confidence:.0f}"

        last      = self._last_signal.get(symbol, {})
        last_sent = self._last_sent_at.get(symbol)

        elapsed: Optional[float] = (
            (datetime.utcnow() - last_sent).total_seconds() / 60
            if last_sent else None
        )

        if elapsed is not None:
            same_direction = last.get("signal_type") == sig_type
            if same_direction and elapsed < self.COOLDOWN_MINUTES:
                return False, f"cooldown_{elapsed:.0f}min"
            if not same_direction and elapsed < self.DIRECTION_CHANGE_COOLDOWN:
                return False, "direction_change_too_fast"

        if last and last.get("signal_type") == sig_type:
            prev_conf = float(last.get("confidence") or 0)
            if confidence - prev_conf < 15:
                if elapsed is not None and elapsed < self.COOLDOWN_MINUTES * 2:
                    return False, "no_significant_improvement"

        return True, "ok"

    def record_sent(self, signal: Dict[str, Any]) -> None:
        symbol = signal.get("symbol", "XAUUSD")
        self._last_signal[symbol]  = signal
        self._last_sent_at[symbol] = datetime.utcnow()

TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_BASE    = f"https://api.telegram.org/bot{TOKEN}"

_registered_chats: Set[str] = set()
_lock = threading.Lock()

_ENV_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
if _ENV_CHAT:
    _registered_chats.add(_ENV_CHAT)

# Filter singleton — shared state persists for the life of the process
_alert_filter = AlertFilter()


# ── Redis stats (best-effort; degrades gracefully when Redis is down) ─────────

_REDIS_SENT_KEY    = "tg:sent_today"
_REDIS_BLOCKED_KEY = "tg:blocked_today"
_REDIS_LAST_KEY    = "tg:last_signal"
_TTL               = 86_400   # one calendar day in seconds

try:
    import redis as _redis_mod
    _redis = _redis_mod.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://redis:6379/0"),
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )
except Exception:
    _redis = None


def _redis_incr(key: str) -> None:
    if _redis is None:
        return
    try:
        pipe = _redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, _TTL)
        pipe.execute()
    except Exception as exc:
        log.debug("Redis incr error (%s): %s", key, exc)


def _redis_get_int(key: str) -> int:
    if _redis is None:
        return 0
    try:
        val = _redis.get(key)
        return int(val) if val else 0
    except Exception:
        return 0


def _redis_set_json(key: str, value: Any) -> None:
    if _redis is None:
        return
    try:
        _redis.set(key, json.dumps(value, default=str), ex=_TTL)
    except Exception as exc:
        log.debug("Redis set error (%s): %s", key, exc)


def _redis_get_json(key: str) -> Optional[Any]:
    if _redis is None:
        return None
    try:
        raw = _redis.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def get_filter_stats() -> Dict[str, Any]:
    """Return today's send/block counters and the last forwarded signal."""
    return {
        "sent_today":    _redis_get_int(_REDIS_SENT_KEY),
        "blocked_today": _redis_get_int(_REDIS_BLOCKED_KEY),
        "last_signal":   _redis_get_json(_REDIS_LAST_KEY),
    }


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _post(method: str, **kwargs) -> Optional[Dict]:
    if not TOKEN:
        return None
    try:
        r    = httpx.post(f"{_BASE}/{method}", json=kwargs, timeout=15)
        data = r.json()
        if not data.get("ok"):
            log.warning("Telegram %s: %s", method, data.get("description"))
            return None
        return data
    except Exception as exc:
        log.warning("Telegram %s error: %s", method, exc)
        return None


def _get(method: str, http_timeout: int = 15, **params) -> Optional[Dict]:
    if not TOKEN:
        return None
    try:
        r    = httpx.get(f"{_BASE}/{method}", params=params, timeout=http_timeout)
        data = r.json()
        return data if data.get("ok") else None
    except Exception as exc:
        log.warning("Telegram %s error: %s", method, exc)
        return None


# ── Send helpers ──────────────────────────────────────────────────────────────

def _kb(*rows) -> Dict:
    """Build inline_keyboard from rows of (text, callback_data) tuples."""
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


_MENU_ROW       = [("🏠 Bosh Menyu", "menu")]
_REFRESH_PRICE  = [("🔄 Yangilash", "price"),  ("📊 Signal",  "signal")]
_REFRESH_NEWS   = [("🔄 Yangilash", "news"),   ("🔍 Tahlil",  "analysis")]
_SIGNAL_ACTIONS = [("🔄 Yangi Signal", "signal")]
_AFTER_SIGNAL   = [("💰 Narx", "price"),       ("📰 Yangilik", "news")]
_ML_ACTIONS     = [("🔄 Yangilash", "ml"),     ("📈 Aniqlik",  "accuracy")]
_ML_EXTRA       = [("⚠️ Patternlar", "patterns"), ("🔁 Retrain", "retrain")]


def send(chat_id: str, text: str, buttons=None) -> bool:
    kwargs: Dict[str, Any] = {
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "Markdown",
    }
    if buttons:
        kwargs["reply_markup"] = buttons
    return _post("sendMessage", **kwargs) is not None


def _answer_cb(callback_query_id: str, text: str = "") -> None:
    _post("answerCallbackQuery", callback_query_id=callback_query_id, text=text)


def broadcast(text: str) -> int:
    count = 0
    with _lock:
        chats = list(_registered_chats)
    for cid in chats:
        if send(cid, text):
            count += 1
    return count


def register_chat(chat_id: str) -> None:
    with _lock:
        _registered_chats.add(str(chat_id))


def get_registered_chats() -> List[str]:
    with _lock:
        return list(_registered_chats)


# ── Command handlers ──────────────────────────────────────────────────────────

def _handle_start(chat_id: str) -> None:
    register_chat(chat_id)
    kb = _kb(
        [("💰 Narx", "price"),    ("📊 Signal",   "signal")],
        [("📰 Yangilik", "news"), ("🔍 Tahlil",   "analysis")],
        [("🤖 ML Tahlil", "ml"),  ("📈 Aniqlik",  "accuracy")],
        [("⚙️ Holat", "status"),  ("❓ Yordam",   "help")],
    )
    send(chat_id,
         f"🤖 *Gold AI Trading Bot*\n\n"
         f"Salom! XAUUSD real-time signallari uchun botga xush kelibsiz.\n\n"
         f"📌 Chat ID: `{chat_id}`\n\n"
         f"Quyidagi tugmalardan birini tanlang:",
         buttons=kb)


def _handle_menu(chat_id: str) -> None:
    kb = _kb(
        [("💰 Narx", "price"),    ("📊 Signal",   "signal")],
        [("📰 Yangilik", "news"), ("🔍 Tahlil",   "analysis")],
        [("🤖 ML Tahlil", "ml"),  ("📈 Aniqlik",  "accuracy")],
        [("⚙️ Holat", "status"),  ("❓ Yordam",   "help")],
    )
    send(chat_id, "🏠 *Bosh Menyu* — kerakli bo'limni tanlang:", buttons=kb)


def _handle_help(chat_id: str) -> None:
    kb = _kb(
        [("💰 Narx", "price"),    ("📊 Signal", "signal")],
        [("🤖 ML Tahlil", "ml"),  ("📈 Aniqlik", "accuracy")],
        [("⚠️ Patternlar", "patterns"), ("🔁 Retrain", "retrain")],
        [("🏠 Bosh Menyu", "menu")],
    )
    send(chat_id,
         "📖 *Buyruqlar*\n\n"
         "/start — Botni ishga tushirish\n"
         "/price — XAUUSD joriy narxi\n"
         "/signal — Yangi signal\n"
         "/news — So'nggi yangiliklar\n"
         "/analysis — TA + SMC tahlil\n"
         "/ml — ML prediction va model holati\n"
         "/accuracy — ML aniqlik statistikasi\n"
         "/patterns — Xato pattern tahlili\n"
         "/retrain — Modelni qo'lda yangilash\n"
         "/status — Tizim holati",
         buttons=kb)


def _handle_price(chat_id: str) -> None:
    try:
        r      = httpx.get("http://localhost:8001/api/v1/market-data/price",
                            params={"symbol": "XAUUSD"}, timeout=10)
        d      = r.json()
        price  = d.get("price") or 0.0
        change = d.get("change_pct") or 0.0
        arrow  = "📈" if change >= 0 else "📉"
        kb     = _kb(_REFRESH_PRICE, _MENU_ROW)
        send(chat_id,
             f"{arrow} *XAUUSD Narxi*\n\n"
             f"💰 `{price:.2f}` USD\n"
             f"📊 O'zgarish: `{change:+.2f}%`\n\n"
             f"_{datetime.utcnow().strftime('%H:%M UTC')}_",
             buttons=kb)
    except Exception as exc:
        send(chat_id, f"⚠️ Narx olishda xatolik: {exc}", buttons=_kb(_MENU_ROW))


def _handle_signal(chat_id: str) -> None:
    send(chat_id, "⏳ Signal generatsiya qilinmoqda...")
    try:
        r = httpx.post("http://localhost:8001/api/v1/signals/generate",
                       json={"symbol": "XAUUSD", "timeframe": "60"}, timeout=30)
        if r.status_code != 200:
            send(chat_id, f"⚠️ Signal xatosi: {r.text[:200]}",
                 buttons=_kb(_SIGNAL_ACTIONS, _MENU_ROW))
            return
        _send_signal_message(chat_id, r.json())
    except Exception as exc:
        send(chat_id, f"⚠️ Signal xatosi: {exc}",
             buttons=_kb(_SIGNAL_ACTIONS, _MENU_ROW))


def _handle_news(chat_id: str) -> None:
    try:
        r     = httpx.get("http://localhost:8001/api/v1/news",
                           params={"limit": 5}, timeout=10)
        items = r.json()
        if not items:
            send(chat_id, "📰 Hozircha yangilik yo'q.", buttons=_kb(_MENU_ROW))
            return
        lines = ["📰 *So'nggi Yangiliklar*\n"]
        for item in items[:5]:
            s     = item.get("sentiment", "neutral")
            emoji = "📈" if s == "bullish" else ("📉" if s == "bearish" else "➖")
            title = item.get("title", "")[:90]
            lines.append(f"{emoji} {title}")
        send(chat_id, "\n".join(lines), buttons=_kb(_REFRESH_NEWS, _MENU_ROW))
    except Exception as exc:
        send(chat_id, f"⚠️ Yangilik xatosi: {exc}", buttons=_kb(_MENU_ROW))


def _handle_analysis(chat_id: str) -> None:
    try:
        snap = httpx.get("http://localhost:8001/api/v1/indicators/snapshot",
                         params={"symbol": "XAUUSD", "timeframe": "60"}, timeout=15).json()
        smc  = httpx.get("http://localhost:8001/api/v1/smc/score",
                         params={"symbol": "XAUUSD", "timeframe": "60"}, timeout=15).json()

        rsi   = snap.get("rsi") or 50.0
        macd  = snap.get("macd") or 0.0
        ema20 = snap.get("ema_20") or 0.0
        ema50 = snap.get("ema_50") or 0.0
        bb_u  = snap.get("bb_upper") or 0.0
        bb_l  = snap.get("bb_lower") or 0.0

        rsi_lbl  = "Oversold 🟢" if rsi < 30 else ("Overbought 🔴" if rsi > 70 else "Neytral ⚪")
        macd_lbl = "Bullish 🟢"  if macd > 0 else "Bearish 🔴"
        smc_dir  = smc.get("direction", "neutral").capitalize()
        smc_sc   = smc.get("score", 50)
        smc_em   = "🟢" if smc_sc > 55 else ("🔴" if smc_sc < 45 else "⚪")

        comp = smc.get("components", {})
        ob   = comp.get("order_block", 50)
        fvg  = comp.get("fvg", 50)
        bos  = comp.get("bos", 50)

        kb = _kb(
            [("📊 Signal Olish", "signal"), ("🔄 Yangilash", "analysis")],
            _MENU_ROW,
        )
        send(chat_id,
             f"📊 *XAUUSD Tahlil (H1)*\n\n"
             f"*Texnik Ko'rsatkichlar*\n"
             f"RSI: `{rsi:.1f}` — {rsi_lbl}\n"
             f"MACD: `{macd:.4f}` — {macd_lbl}\n"
             f"EMA20: `{ema20:.2f}` | EMA50: `{ema50:.2f}`\n"
             f"BB: `{bb_l:.2f}` — `{bb_u:.2f}`\n\n"
             f"*SMC Tahlil* {smc_em}\n"
             f"Yo'nalish: *{smc_dir}* | Ball: `{smc_sc:.0f}/100`\n"
             f"OB: `{ob:.0f}` | FVG: `{fvg:.0f}` | BOS: `{bos:.0f}`\n\n"
             f"_{datetime.utcnow().strftime('%H:%M UTC')}_",
             buttons=kb)
    except Exception as exc:
        send(chat_id, f"⚠️ Tahlil xatosi: {exc}", buttons=_kb(_MENU_ROW))


def _handle_ml(chat_id: str) -> None:
    """So'nggi ML prediction va model holati."""
    send(chat_id, "⏳ ML prediction yuklanmoqda...")
    try:
        r = httpx.post(
            "http://localhost:8001/api/v1/ml/predict",
            json={"symbol": "XAUUSD", "timeframe": "60"},
            timeout=20,
        )
        d = r.json() if r.status_code == 200 else {}

        direction   = d.get("direction", "—")
        buy_pct     = d.get("buy_pct") or d.get("probabilities", {}).get("bullish", 0)
        sell_pct    = d.get("sell_pct") or d.get("probabilities", {}).get("bearish", 0)
        neutral_pct = d.get("neutral_pct") or d.get("probabilities", {}).get("neutral", 0)
        score       = d.get("score") or d.get("confidence", 0)
        models_used = d.get("models_used", d.get("models_count", 0))
        available   = d.get("model_available", d.get("status") == "ok")

        dir_em = "🟢" if direction == "bullish" else ("🔴" if direction == "bearish" else "⚪")

        def _bar(v):
            v = float(v or 0)
            filled = round(v / 10)
            return "█" * filled + "░" * (10 - filled)

        status_txt = "✅ Tayyor" if available else "⚠️ Model o'qitilmagan"

        # Tarix oxirgisini ham ko'rsatamiz
        hist_r = httpx.get(
            "http://localhost:8001/api/v1/ml/feedback/history",
            params={"symbol": "XAUUSD", "timeframe": "60", "limit": 3},
            timeout=10,
        )
        hist_rows = hist_r.json().get("results", []) if hist_r.status_code == 200 else []

        lines = [
            f"🤖 *ML Prediction — XAUUSD H1*\n",
            f"*Joriy Prediction*",
            f"Yo'nalish: {dir_em} *{direction.upper()}*",
            f"Score:     `{float(score or 0):.1f}%`",
            f"Modellar:  `{models_used}` ta",
            f"Holat:     `{status_txt}`\n",
            f"*Ehtimollik*",
            f"`BUY  {_bar(buy_pct)} {float(buy_pct or 0):.1f}%`",
            f"`SELL {_bar(sell_pct)} {float(sell_pct or 0):.1f}%`",
            f"`NEUT {_bar(neutral_pct)} {float(neutral_pct or 0):.1f}%`",
        ]

        if hist_rows:
            lines.append("\n*Oxirgi natijalar*")
            for row in hist_rows:
                ok_em  = "✅" if row.get("was_correct") else "❌"
                pred   = row.get("predicted_dir", "?")
                actual = row.get("actual_dir", "?")
                chg    = row.get("price_change_pct", 0) or 0
                lines.append(f"{ok_em} {pred} → {actual} `{chg:+.2f}%`")

        lines.append(f"\n_{datetime.utcnow().strftime('%H:%M UTC')}_")

        kb = _kb(_ML_ACTIONS, _ML_EXTRA, _MENU_ROW)
        send(chat_id, "\n".join(lines), buttons=kb)

    except Exception as exc:
        send(chat_id, f"⚠️ ML xatosi: {exc}", buttons=_kb(_MENU_ROW))


def _handle_accuracy(chat_id: str) -> None:
    """ML aniqlik statistikasi — session bo'yicha."""
    try:
        r = httpx.get(
            "http://localhost:8001/api/v1/ml/feedback/accuracy",
            params={"symbol": "XAUUSD", "timeframe": "60", "last_n": 100},
            timeout=10,
        )
        d = r.json() if r.status_code == 200 else {}

        acc = d.get("accuracy")
        if acc is None:
            send(chat_id,
                 "📊 *ML Aniqlik*\n\nHali yetarli prediction natijasi yo'q.\n"
                 "Tizim candle ma'lumotlarini to'plagandan keyin avtomatik hisoblaydi.",
                 buttons=_kb([("🔄 Yangilash", "accuracy"), ("🤖 ML", "ml")], _MENU_ROW))
            return

        correct = d.get("correct", 0)
        wrong   = d.get("wrong", 0)
        total   = d.get("count", 0)
        by_ses  = d.get("session_accuracy", {})

        def _acc_em(a):
            return "🟢" if a >= 0.6 else ("🟡" if a >= 0.5 else "🔴")

        lines = [
            f"📊 *ML Aniqlik — XAUUSD H1*\n",
            f"Umumiy:  {_acc_em(acc)} `{acc * 100:.1f}%`",
            f"To'g'ri: `{correct}` / `{total}` ta\n",
        ]

        if by_ses:
            lines.append("*Sessiya bo'yicha*")
            for ses, a in sorted(by_ses.items(), key=lambda x: -x[1]):
                ses_em = "🌅" if ses == "london" else ("🗽" if ses == "newyork" else "🌙")
                lines.append(f"{ses_em} {ses.capitalize()}: `{a * 100:.1f}%`")

        lines.append(f"\n_{datetime.utcnow().strftime('%H:%M UTC')}_")
        kb = _kb([("🔄 Yangilash", "accuracy"), ("⚠️ Patternlar", "patterns")],
                 [("🤖 ML", "ml"), ("🔁 Retrain", "retrain")], _MENU_ROW)
        send(chat_id, "\n".join(lines), buttons=kb)

    except Exception as exc:
        send(chat_id, f"⚠️ Aniqlik xatosi: {exc}", buttons=_kb(_MENU_ROW))


def _handle_patterns(chat_id: str) -> None:
    """Xato prediction patternlari — MLTrainer penalty uchun."""
    try:
        r = httpx.get(
            "http://localhost:8001/api/v1/ml/feedback/error-patterns",
            params={"symbol": "XAUUSD", "timeframe": "60", "min_occurrences": 2},
            timeout=10,
        )
        d = r.json() if r.status_code == 200 else {}
        patterns = d.get("patterns", [])

        if not patterns:
            send(chat_id,
                 "⚠️ *Xato Patternlar*\n\nHali kamida 2 marta takrorlangan xato pattern topilmadi.\n"
                 "Bu yaxshi belgi — model xatolardan o'rganmoqda.",
                 buttons=_kb([("🔄 Yangilash", "patterns"), ("📈 Aniqlik", "accuracy")], _MENU_ROW))
            return

        lines = [f"⚠️ *Xato Patternlar — XAUUSD H1* ({len(patterns)} ta)\n"]
        for i, p in enumerate(patterns[:8], 1):
            err  = p.get("error_rate", 0) or 0
            occ  = p.get("occurrences", 0)
            pen  = p.get("weight_penalty", 0) or 0
            pt   = p.get("pattern_type", "?").replace("_", " ").title()
            ses  = p.get("session") or "—"
            lines.append(
                f"{i}. *{pt}*\n"
                f"   Xato: `{err * 100:.0f}%` | Soni: `{occ}` | Penalty: `{pen:.2f}`\n"
                f"   Sessiya: `{ses}`"
            )

        lines.append(f"\n_Model bu patternlarda sample weight kamaytiradi_")
        lines.append(f"_{datetime.utcnow().strftime('%H:%M UTC')}_")

        kb = _kb([("🔄 Yangilash", "patterns"), ("🔁 Retrain", "retrain")],
                 [("📈 Aniqlik", "accuracy"), ("🤖 ML", "ml")], _MENU_ROW)
        send(chat_id, "\n".join(lines), buttons=kb)

    except Exception as exc:
        send(chat_id, f"⚠️ Pattern xatosi: {exc}", buttons=_kb(_MENU_ROW))


def _handle_retrain(chat_id: str) -> None:
    """Modelni qo'lda qayta o'qitish."""
    send(chat_id, "🔁 Model qayta o'qitilmoqda... Bu 30–60 soniya olishi mumkin.")
    try:
        r = httpx.post(
            "http://localhost:8001/api/v1/ml/feedback/retrain",
            params={"symbol": "XAUUSD", "timeframe": "60"},
            timeout=120,
        )
        d = r.json() if r.status_code == 200 else {"retrained": False, "reason": r.text[:200]}

        if d.get("retrained"):
            metrics  = d.get("metrics", {})
            version  = metrics.get("version", "?")
            samples  = metrics.get("sample_count", 0)
            trained  = metrics.get("trained_models", [])
            patterns = d.get("error_patterns_applied", 0)
            lines = [
                "✅ *Model muvaffaqiyatli yangilandi!*\n",
                f"Versiya:   `{version}`",
                f"Namunalar: `{samples}` ta",
                f"Modellar:  `{', '.join(trained) if trained else '—'}`",
                f"Penaltylar: `{patterns}` ta xato pattern qo'llandi\n",
                f"_Model keyingi predictiondan boshlab yangi versiyadan foydalanadi_",
                f"_{datetime.utcnow().strftime('%H:%M UTC')}_",
            ]
            send(chat_id, "\n".join(lines),
                 buttons=_kb([("🤖 ML", "ml"), ("📈 Aniqlik", "accuracy")], _MENU_ROW))
        else:
            reason_map = {
                "too_soon":           "Oxirgi retrainingdan 30 daqiqa o'tmagan",
                "trigger_not_met":    "Trigger shartlari bajarilmagan (xato/candle kam)",
                "insufficient_candles": "Yetarli candle yo'q (200 dan kam)",
                "dataset_too_small":  "Dataset juda kichik (100 dan kam namuna)",
            }
            reason = d.get("reason", "unknown")
            reason_txt = reason_map.get(reason, reason)
            send(chat_id,
                 f"ℹ️ *Retrain bajarilmadi*\n\nSabab: `{reason_txt}`",
                 buttons=_kb([("🔁 Majburiy Retrain", "retrain"), ("🤖 ML", "ml")], _MENU_ROW))

    except Exception as exc:
        send(chat_id, f"⚠️ Retrain xatosi: {exc}", buttons=_kb(_MENU_ROW))


def _handle_status(chat_id: str) -> None:
    try:
        health = httpx.get("http://localhost:8001/api/v1/health", timeout=5).json()
        ok     = health.get("status") == "ok"
        chats  = len(get_registered_chats())
        stats  = get_filter_stats()
        kb = _kb([("🔄 Yangilash", "status")], _MENU_ROW)
        send(chat_id,
             f"🤖 *Tizim Holati*\n\n"
             f"Backend: `{'✅ Ishlayapti' if ok else '❌ Xato'}`\n"
             f"Versiya: `{health.get('version', '?')}`\n"
             f"Faol chatlar: `{chats}`\n\n"
             f"🔔 *Bugungi Signallar*\n"
             f"Yuborildi: `{stats['sent_today']}`\n"
             f"Bloklandi: `{stats['blocked_today']}`\n\n"
             f"_{datetime.utcnow().strftime('%H:%M UTC')}_",
             buttons=kb)
    except Exception:
        send(chat_id, "❌ Backend bilan bog'lanib bo'lmadi.", buttons=_kb(_MENU_ROW))


def _send_signal_message(chat_id: str, d: Dict[str, Any]) -> None:
    sig  = d.get("signal_type", "NEUTRAL")
    conf = d.get("confidence") or 0

    if sig == "BUY":
        sig_header = "🟢 ═══════════════════\n📈  *BUY — SOTIB OL*\n🟢 ═══════════════════"
    elif sig == "SELL":
        sig_header = "🔴 ═══════════════════\n📉  *SELL — SOT*\n🔴 ═══════════════════"
    else:
        sig_header = "⚪ ═══════════════════\n⏸  *NO TRADE — Kuting*\n⚪ ═══════════════════"

    def _f(v): return f"{v:.2f}" if v is not None else "—"

    entry = d.get("entry")
    sl    = d.get("stop_loss")
    tp    = d.get("take_profit")
    rr    = d.get("rr")
    tech  = d.get("technical_score") or 50
    smc   = d.get("smc_score") or 50
    ml    = d.get("ml_score") or 50
    news  = d.get("news_score") or 50
    rsn   = (d.get("reasoning") or "")[:180]

    def _bar(v):
        filled = round(v / 10)
        return "█" * filled + "░" * (10 - filled)

    if sig in ("BUY", "SELL"):
        trade_section = (
            f"💰 *Savdo Rejasi*\n"
            f"Kirish:      `{_f(entry)}`\n"
            f"Stop Loss:   `{_f(sl)}`\n"
            f"Take Profit: `{_f(tp)}`\n"
            f"R/R:         `{f'{rr:.2f}R' if rr else '—'}`\n\n"
        )
    else:
        trade_section = "ℹ️ _Bozor yo'nalishi aniq emas. Savdo ochish tavsiya etilmaydi._\n\n"

    kb = _kb(_SIGNAL_ACTIONS, _AFTER_SIGNAL, _MENU_ROW)
    send(chat_id,
         f"{sig_header}\n"
         f"*XAUUSD · H1 | {datetime.utcnow().strftime('%d %b %H:%M UTC')}*\n\n"
         f"{trade_section}"
         f"📊 *Ishonch: {conf:.1f}%*\n"
         f"`TA   {_bar(tech)} {tech:.0f}`\n"
         f"`SMC  {_bar(smc)} {smc:.0f}`\n"
         f"`ML   {_bar(ml)} {ml:.0f}`\n"
         f"`News {_bar(news)} {news:.0f}`\n\n"
         f"📝 _{rsn}_",
         buttons=kb)


# ── ML broadcast (called from realtime_predictor when high-confidence prediction) ──

def alert_ml_prediction(
    symbol: str,
    timeframe: str,
    direction: str,
    buy_pct: float,
    sell_pct: float,
    score: float,
    models_used: int,
) -> int:
    """
    Faqat yuqori ishonchli (score ≥ 70) ML predictionlarni broadcast qiladi.
    """
    if score < 70:
        return 0
    if direction == "neutral":
        return 0

    dir_em = "🟢" if direction == "bullish" else "🔴"
    tf_lbl = f"H{int(timeframe) // 60}" if int(timeframe) >= 60 else f"M{timeframe}"

    def _bar(v):
        filled = round(float(v or 0) / 10)
        return "█" * filled + "░" * (10 - filled)

    text = (
        f"{dir_em} *ML Prediction — {symbol} {tf_lbl}*\n\n"
        f"Yo'nalish: *{direction.upper()}*\n"
        f"Score: `{score:.1f}%` | Modellar: `{models_used}`\n\n"
        f"`BUY  {_bar(buy_pct)} {buy_pct:.1f}%`\n"
        f"`SELL {_bar(sell_pct)} {sell_pct:.1f}%`\n\n"
        f"_ML auto-prediction | {datetime.utcnow().strftime('%H:%M UTC')}_"
    )
    return broadcast(text)


# ── Public alert (called from signals router after signal generation) ─────────

def alert_signal(signal: Dict[str, Any]) -> int:
    """
    Broadcast a trading signal to all registered chats after filter check.
    Returns the number of chats the signal was delivered to (0 if filtered).
    """
    should, reason = _alert_filter.should_send(signal)
    if not should:
        log.debug(
            "Signal filtered [%s %s conf=%.0f]: %s",
            signal.get("symbol"), signal.get("signal_type"),
            float(signal.get("confidence") or 0), reason,
        )
        _redis_incr(_REDIS_BLOCKED_KEY)
        return 0

    count = 0
    for cid in get_registered_chats():
        _send_signal_message(cid, signal)
        count += 1

    if count > 0:
        _alert_filter.record_sent(signal)
        _redis_incr(_REDIS_SENT_KEY)
        _redis_set_json(_REDIS_LAST_KEY, {
            "symbol":      signal.get("symbol"),
            "signal_type": signal.get("signal_type"),
            "confidence":  signal.get("confidence"),
            "sent_at":     datetime.utcnow().isoformat(),
        })

    return count


def send_daily_summary(signals: List[Dict[str, Any]]) -> int:
    """Broadcast a one-line digest of signals to all registered chats."""
    buy_count  = sum(1 for s in signals if s.get("signal_type") == "BUY")
    sell_count = sum(1 for s in signals if s.get("signal_type") == "SELL")
    no_trade   = sum(1 for s in signals if s.get("signal_type") == "NO TRADE")
    n          = len(signals)
    text = (
        f"📊 *Gold AI Daily: {n} signals | "
        f"{buy_count} BUY {sell_count} SELL {no_trade} skipped*\n"
        f"_{datetime.utcnow().strftime('%Y-%m-%d UTC')}_"
    )
    return broadcast(text)


# ── Polling ───────────────────────────────────────────────────────────────────

_COMMANDS = {
    "/start":    _handle_start,
    "/help":     _handle_help,
    "/price":    _handle_price,
    "/signal":   _handle_signal,
    "/news":     _handle_news,
    "/analysis": _handle_analysis,
    "/status":   _handle_status,
    "/ml":       _handle_ml,
    "/accuracy": _handle_accuracy,
    "/patterns": _handle_patterns,
    "/retrain":  _handle_retrain,
}

_CALLBACKS = {
    "menu":     _handle_menu,
    "price":    _handle_price,
    "signal":   _handle_signal,
    "news":     _handle_news,
    "analysis": _handle_analysis,
    "status":   _handle_status,
    "help":     _handle_help,
    "ml":       _handle_ml,
    "accuracy": _handle_accuracy,
    "patterns": _handle_patterns,
    "retrain":  _handle_retrain,
}

_polling_thread: Optional[threading.Thread] = None


def _polling_loop() -> None:
    offset = 0
    log.info("Telegram polling started")
    while True:
        try:
            data = _get(
                "getUpdates",
                http_timeout=40,
                offset=offset,
                timeout=35,
                allowed_updates=["message", "callback_query"],
            )
            if not (data and data.get("result")):
                continue

            for upd in data["result"]:
                offset = upd["update_id"] + 1

                # inline button press
                cb = upd.get("callback_query")
                if cb:
                    cb_id   = cb["id"]
                    chat_id = str(cb["message"]["chat"]["id"])
                    action  = cb.get("data", "")
                    register_chat(chat_id)
                    _answer_cb(cb_id)
                    handler = _CALLBACKS.get(action)
                    if handler:
                        try:
                            handler(chat_id)
                        except Exception:
                            log.exception("Callback %s failed", action)
                    continue

                # text command
                msg     = upd.get("message", {})
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text    = (msg.get("text") or "").strip()
                if not chat_id or not text:
                    continue
                register_chat(chat_id)
                cmd     = text.split("@")[0].split(" ")[0].lower()
                handler = _COMMANDS.get(cmd)
                if handler:
                    try:
                        handler(chat_id)
                    except Exception:
                        log.exception("Command %s failed", cmd)
                else:
                    send(chat_id, "❓ Noma'lum buyruq.", buttons=_kb(_MENU_ROW))

        except Exception:
            log.exception("Polling error, retry in 5s")
            time.sleep(5)


def start_polling() -> None:
    global _polling_thread
    if not TOKEN:
        log.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
        return
    if _polling_thread and _polling_thread.is_alive():
        return
    _polling_thread = threading.Thread(
        target=_polling_loop, daemon=True, name="telegram-polling"
    )
    _polling_thread.start()
    log.info("Telegram bot polling thread started")
