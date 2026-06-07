"""
Telegram bot for Gold AI Trading Intelligence.
Commands: /start /help /gold /chart /signal /news /analysis /status

Requires: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars.
Uses direct HTTP API calls (no heavy dependency).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
_BASE_URL          = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


# ── Alert filter ──────────────────────────────────────────────────────────────

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
        self._last_signal:   Dict[str, Any]      = {}   # keyed by symbol
        self._last_sent_at:  Dict[str, datetime]  = {}

    def should_send(self, signal: Dict[str, Any]) -> tuple[bool, str]:
        """Return (should_send, reason_code)."""
        symbol     = signal.get("symbol", "XAUUSD")
        sig_type   = signal.get("signal_type")
        confidence = float(signal.get("confidence") or 0)

        # Rule 1 — never send NO TRADE
        if sig_type == "NO TRADE":
            return False, "no_trade"

        # Rule 2 — confidence gate
        if confidence < self.MIN_CONFIDENCE:
            return False, f"low_confidence_{confidence:.0f}"

        last      = self._last_signal.get(symbol, {})
        last_sent = self._last_sent_at.get(symbol)

        # Compute elapsed once; None when this symbol has never been sent
        elapsed: Optional[float] = (
            (datetime.utcnow() - last_sent).total_seconds() / 60
            if last_sent else None
        )

        # Rule 3 — directional cooldowns
        if elapsed is not None:
            same_direction = last.get("signal_type") == sig_type
            if same_direction and elapsed < self.COOLDOWN_MINUTES:
                return False, f"cooldown_{elapsed:.0f}min"
            if not same_direction and elapsed < self.DIRECTION_CHANGE_COOLDOWN:
                return False, "direction_change_too_fast"

        # Rule 4 — re-alert only on meaningful confidence improvement
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


# Module-level singleton shared by TelegramBot
alert_filter = AlertFilter()


# ── Bot class ─────────────────────────────────────────────────────────────────

class TelegramBot:
    """
    Lightweight Telegram bot using direct HTTP API calls (no heavy dependency).
    For a full bot server, integrate with python-telegram-bot's Application.
    """

    def send_message(self, chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
        if not TELEGRAM_BOT_TOKEN:
            log.warning("TELEGRAM_BOT_TOKEN not set — message not sent")
            return False
        try:
            resp = httpx.post(
                f"{_BASE_URL}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception:
            log.exception("Failed to send Telegram message")
            return False

    def send_signal_alert(self, signal: Dict[str, Any]) -> bool:
        """Format and send a trading signal alert, subject to AlertFilter rules."""
        should, reason = alert_filter.should_send(signal)
        if not should:
            log.debug("Signal alert suppressed [%s]: %s", signal.get("symbol"), reason)
            return False

        conf = float(signal.get("confidence") or 0)
        emoji = (
            "🟢" if signal.get("signal_type") == "BUY"
            else ("🔴" if signal.get("signal_type") == "SELL" else "⚪")
        )
        text = (
            f"{emoji} *GOLD AI SIGNAL*\n"
            f"Symbol: `{signal.get('symbol', 'XAUUSD')}`\n"
            f"Signal: *{signal.get('signal_type', 'N/A')}*\n"
            f"Timeframe: `{signal.get('timeframe', 'N/A')}`\n\n"
            f"💰 *Trade Plan*\n"
            f"Entry: `{signal.get('entry', 'N/A')}`\n"
            f"Stop Loss: `{signal.get('stop_loss', 'N/A')}`\n"
            f"Take Profit: `{signal.get('take_profit', 'N/A')}`\n"
            f"R/R: `{signal.get('risk_reward', 'N/A')}`\n\n"
            f"📊 *Confidence: {conf:.1f}%*\n\n"
            f"🧠 *Score Breakdown*\n"
            f"Technical: {signal.get('technical_score', 50):.0f}/100\n"
            f"SMC: {signal.get('smc_score', 50):.0f}/100\n"
            f"ML: {signal.get('ml_score', 50):.0f}/100\n"
            f"News: {signal.get('news_score', 50):.0f}/100\n\n"
            f"📝 {(signal.get('reasoning') or 'No reasoning available')[:200]}\n\n"
            f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | "
            f"Confidence: {conf:.0f}% | Filter: active_"
        )

        sent = self.send_message(TELEGRAM_CHAT_ID, text)
        if sent:
            alert_filter.record_sent(signal)
        return sent

    def send_daily_summary(self, signals: List[Dict[str, Any]]) -> bool:
        """Send a one-line digest of all signals from the last 24 hours."""
        buy_count  = sum(1 for s in signals if s.get("signal_type") == "BUY")
        sell_count = sum(1 for s in signals if s.get("signal_type") == "SELL")
        no_trade   = sum(1 for s in signals if s.get("signal_type") == "NO TRADE")
        n = len(signals)
        text = (
            f"📊 *Gold AI Daily Summary*\n"
            f"{n} signals | {buy_count} BUY | {sell_count} SELL | {no_trade} skipped\n"
            f"_{datetime.utcnow().strftime('%Y-%m-%d UTC')}_"
        )
        return self.send_message(TELEGRAM_CHAT_ID, text)

    def send_news_alert(self, title: str, impact_score: int, direction: str, confidence: float) -> bool:
        emoji = "📈" if direction == "bullish" else ("📉" if direction == "bearish" else "📰")
        text = (
            f"{emoji} *GOLD NEWS ALERT*\n"
            f"{title}\n\n"
            f"Impact: `{impact_score}/10`\n"
            f"Direction: *{direction.upper()}*\n"
            f"Confidence: `{confidence:.1f}%`\n\n"
            f"_Gold AI News Intelligence_"
        )
        return self.send_message(TELEGRAM_CHAT_ID, text)

    def send_status(self, status: Dict[str, Any]) -> bool:
        text = (
            f"🤖 *GOLD AI STATUS*\n"
            f"Backend: `{'✅ Online' if status.get('online') else '❌ Offline'}`\n"
            f"MT4: `{'✅ Connected' if status.get('mt4_connected') else '⚠️ Disconnected'}`\n"
            f"Last Signal: `{status.get('last_signal', 'N/A')}`\n"
            f"Signals Today: `{status.get('signals_today', 0)}`\n"
            f"News Articles: `{status.get('news_count', 0)}`\n\n"
            f"_Updated: {datetime.utcnow().strftime('%H:%M UTC')}_"
        )
        return self.send_message(TELEGRAM_CHAT_ID, text)

    def handle_command(self, command: str, chat_id: str) -> None:
        """Route incoming Telegram commands."""
        handlers = {
            "/start":  self._cmd_start,
            "/help":   self._cmd_help,
            "/status": self._cmd_status,
        }
        handler = handlers.get(command.split("@")[0])
        if handler:
            handler(chat_id)
        else:
            self.send_message(chat_id, "Unknown command. Use /help to see available commands.")

    def _cmd_start(self, chat_id: str) -> None:
        self.send_message(chat_id,
            "👋 *Welcome to Gold AI Trading Intelligence!*\n\n"
            "I provide real-time XAUUSD analysis and trading signals.\n\n"
            "Use /help to see all commands.")

    def _cmd_help(self, chat_id: str) -> None:
        self.send_message(chat_id,
            "📖 *Available Commands*\n\n"
            "/start — Welcome message\n"
            "/help — This help menu\n"
            "/gold — Current XAUUSD price & trend\n"
            "/chart — Latest chart pattern analysis\n"
            "/signal — Generate a new trading signal\n"
            "/news — Latest gold news sentiment\n"
            "/analysis — AI market analysis\n"
            "/status — System status")

    def _cmd_status(self, chat_id: str) -> None:
        self.send_status({
            "online": True, "mt4_connected": False,
            "last_signal": "N/A", "signals_today": 0, "news_count": 0,
        })

    def process_webhook(self, update: Dict[str, Any]) -> None:
        """Process a Telegram webhook update."""
        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))
        text    = message.get("text", "")
        if text.startswith("/"):
            self.handle_command(text.strip(), chat_id)


telegram_bot = TelegramBot()
