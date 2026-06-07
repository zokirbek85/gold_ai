"""
AI Analyst — uses Claude or OpenAI to generate narrative market analysis,
explain signals, and produce daily bias summaries.

Requires one of:
  ANTHROPIC_API_KEY  — uses claude-sonnet-4-6
  OPENAI_API_KEY     — uses gpt-4o
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are an expert gold market analyst specializing in XAUUSD.
You analyze technical data, smart money concepts, news, and macroeconomic events.
Your analysis must be:
- Precise and evidence-based
- Risk-aware (never ignore risk management)
- Actionable for professional traders
- Structured: Market Summary, Bias, Key Levels, Risk Commentary

Never fabricate price data. Always acknowledge uncertainty.
"""


class AIAnalyst:
    def __init__(self) -> None:
        self._anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        self._openai_key = os.environ.get("OPENAI_API_KEY")

    def _build_context(self, signal_data: Dict[str, Any], market_context: Optional[Dict[str, Any]] = None) -> str:
        ctx = f"""
TRADING SIGNAL DATA (as of {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}):

Symbol: {signal_data.get('symbol', 'XAUUSD')}
Timeframe: {signal_data.get('timeframe', 'H1')}
Signal Type: {signal_data.get('signal_type', 'N/A')}
Confidence: {signal_data.get('confidence', 0):.1f}%

SCORE BREAKDOWN:
- Technical Score: {signal_data.get('technical_score', 50):.1f}/100
- SMC Score: {signal_data.get('smc_score', 50):.1f}/100
- ML Score: {signal_data.get('ml_score', 50):.1f}/100
- News Score: {signal_data.get('news_score', 50):.1f}/100
- Economic Score: {signal_data.get('economic_score', 50):.1f}/100
- Composite Score: {signal_data.get('composite_score', 50):.1f}/100

TRADE PLAN:
- Entry: {signal_data.get('entry', 'N/A')}
- Stop Loss: {signal_data.get('stop_loss', 'N/A')}
- Take Profit: {signal_data.get('take_profit', 'N/A')}
- Risk/Reward: {signal_data.get('risk_reward', 'N/A')}

SIGNAL REASONING: {signal_data.get('reasoning', 'N/A')}
"""
        if market_context:
            ctx += f"\n\nADDITIONAL CONTEXT:\n{market_context}"
        return ctx

    def analyze_signal(
        self,
        signal_data: Dict[str, Any],
        market_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate AI analysis for a trading signal."""
        context = self._build_context(signal_data, market_context)
        prompt = f"""Please analyze this XAUUSD trading signal and provide:
1. Market Summary (2-3 sentences)
2. Daily Bias (Bullish/Bearish/Neutral + explanation)
3. Signal Explanation (why this signal was generated)
4. Key Levels to Watch
5. Risk Commentary
6. Confidence Analysis

{context}
"""
        response = self._call_ai(prompt)
        return {
            "symbol": signal_data.get("symbol", "XAUUSD"),
            "signal_id": signal_data.get("id"),
            "analysis": response,
            "model": self._get_model_name(),
            "created_at": datetime.utcnow().isoformat(),
        }

    def daily_bias(self, candle_summary: str, news_summary: str, econ_summary: str) -> str:
        """Generate a daily market bias analysis."""
        prompt = f"""Generate a professional XAUUSD daily bias analysis for today.

MARKET DATA SUMMARY:
{candle_summary}

RECENT NEWS:
{news_summary}

ECONOMIC EVENTS:
{econ_summary}

Provide:
1. Overall Bias (Bullish/Bearish/Neutral)
2. Key Support and Resistance Levels
3. Catalysts to Watch
4. Risk Scenarios
Keep it under 300 words. Professional tone.
"""
        return self._call_ai(prompt)

    def _call_ai(self, prompt: str) -> str:
        # Try Anthropic first
        if self._anthropic_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=self._anthropic_key)
                message = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1024,
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                return message.content[0].text
            except Exception:
                log.exception("Anthropic API call failed — trying OpenAI")

        # Fallback to OpenAI
        if self._openai_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=self._openai_key)
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    max_tokens=1024,
                )
                return response.choices[0].message.content
            except Exception:
                log.exception("OpenAI API call failed")

        return "AI analysis unavailable — configure ANTHROPIC_API_KEY or OPENAI_API_KEY."

    def _get_model_name(self) -> str:
        if self._anthropic_key:
            return "claude-sonnet-4-6"
        if self._openai_key:
            return "gpt-4o"
        return "none"


ai_analyst = AIAnalyst()
