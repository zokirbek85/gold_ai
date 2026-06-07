"""
Signal Scorer — combines all analysis layers into a final trading signal.

Final Score Formula:
    Technical Score  35%
    SMC Score        25%
    ML Score         20%
    News Score       10%
    Economic Score   10%

Output: BUY | SELL | NO TRADE + confidence + trade plan
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.indicators.calculator import calculator as ind_calc
from src.indicators.repository import IndicatorRepository
from src.patterns.candlestick import candlestick_detector
from src.patterns.chart import chart_detector
from src.risk_management.calculator import risk_calculator
from src.smc.engine import smc_engine

log = logging.getLogger(__name__)

WEIGHTS = {
    "technical": 0.35,
    "smc": 0.25,
    "ml": 0.20,
    "news": 0.10,
    "economic": 0.10,
}

SIGNAL_THRESHOLD_BUY = 62.0
SIGNAL_THRESHOLD_SELL = 38.0


class SignalScorer:
    def _technical_score(self, candles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Score 0–100. >50 = bullish, <50 = bearish."""
        if len(candles) < 20:
            return {"score": 50.0, "direction": "neutral", "details": {}}

        indicators = ind_calc.compute_all(candles)
        close = float(candles[-1]["close"])

        bull_signals = 0
        bear_signals = 0
        total_signals = 0

        # EMA trend alignment
        for period_key in ["EMA_20", "EMA_50", "EMA_100", "EMA_200"]:
            val = indicators.get(period_key)
            if val is not None:
                total_signals += 1
                if close > val:
                    bull_signals += 1
                else:
                    bear_signals += 1

        # RSI
        rsi = indicators.get("RSI_14")
        if rsi is not None:
            total_signals += 1
            if rsi < 30:
                bull_signals += 2  # oversold — bullish
                total_signals += 1
            elif rsi > 70:
                bear_signals += 2  # overbought — bearish
                total_signals += 1
            elif 40 < rsi < 60:
                pass  # neutral
            elif rsi > 55:
                bull_signals += 1
            else:
                bear_signals += 1

        # MACD
        macd_line = indicators.get("MACD_line")
        macd_sig = indicators.get("MACD_signal")
        if macd_line is not None and macd_sig is not None:
            total_signals += 1
            if macd_line > macd_sig:
                bull_signals += 1
            else:
                bear_signals += 1

        # Stochastic
        k = indicators.get("STOCH_K")
        if k is not None:
            total_signals += 1
            if k < 20:
                bull_signals += 1
            elif k > 80:
                bear_signals += 1

        # ADX
        adx = indicators.get("ADX")
        plus_di = indicators.get("PLUS_DI")
        minus_di = indicators.get("MINUS_DI")
        if adx and adx > 25 and plus_di is not None and minus_di is not None:
            total_signals += 1
            if plus_di > minus_di:
                bull_signals += 1
            else:
                bear_signals += 1

        # Bollinger Band position
        bb_upper = indicators.get("BB_upper")
        bb_lower = indicators.get("BB_lower")
        if bb_upper and bb_lower:
            total_signals += 1
            if close < bb_lower:
                bull_signals += 1  # below lower band — reversal
            elif close > bb_upper:
                bear_signals += 1  # above upper band — reversal

        # Pattern bonus
        candlestick_patterns = candlestick_detector.detect_all(candles[-5:])
        chart_patterns = chart_detector.detect_all(candles)
        for p in candlestick_patterns + chart_patterns:
            total_signals += 1
            if p["direction"] == "bullish":
                bull_signals += p.get("confidence", 0.5)
            elif p["direction"] == "bearish":
                bear_signals += p.get("confidence", 0.5)

        total_weight = bull_signals + bear_signals
        if total_weight == 0 or total_signals == 0:
            score = 50.0
            direction = "neutral"
        else:
            score = bull_signals / total_weight * 100
            direction = "bullish" if score > 55 else ("bearish" if score < 45 else "neutral")

        return {
            "score": round(score, 1),
            "direction": direction,
            "details": {
                "indicators": {k: v for k, v in indicators.items() if v is not None},
                "patterns": [p["name"] for p in candlestick_patterns + chart_patterns],
            },
        }

    def generate(
        self,
        candles: List[Dict[str, Any]],
        smc_score: Optional[Dict[str, Any]] = None,
        ml_score: Optional[Dict[str, Any]] = None,
        news_score: Optional[Dict[str, Any]] = None,
        economic_score: Optional[Dict[str, Any]] = None,
        account_balance: float = 10000.0,
    ) -> Dict[str, Any]:
        """
        Generate a trading signal by combining all score layers.
        Each score dict: {"direction": "bullish"|"bearish"|"neutral", "score": float 0-100}
        """
        tech = self._technical_score(candles)

        def _normalize(score_dict: Optional[Dict[str, Any]]) -> float:
            if not score_dict:
                return 50.0
            return float(score_dict.get("score", 50.0))

        tech_score = _normalize(tech)
        smc_val = _normalize(smc_score)
        ml_val = _normalize(ml_score)
        news_val = _normalize(news_score)
        econ_val = _normalize(economic_score)

        # Weighted composite score (>50 bullish, <50 bearish)
        composite = (
            tech_score * WEIGHTS["technical"]
            + smc_val * WEIGHTS["smc"]
            + ml_val * WEIGHTS["ml"]
            + news_val * WEIGHTS["news"]
            + econ_val * WEIGHTS["economic"]
        )

        if composite >= SIGNAL_THRESHOLD_BUY:
            signal_type = "BUY"
            direction = "bullish"
        elif composite <= SIGNAL_THRESHOLD_SELL:
            signal_type = "SELL"
            direction = "bearish"
        else:
            signal_type = "NO TRADE"
            direction = "neutral"

        confidence = abs(composite - 50) * 2  # 0–100

        trade_plan = {}
        if signal_type in ("BUY", "SELL") and candles:
            trade_plan = risk_calculator.build_trade_plan(
                candles=candles,
                direction=direction,
                account_balance=account_balance,
            )
            risk_check = risk_calculator.passes_risk_filter(trade_plan)
            if not risk_check["passed"]:
                log.warning("Signal blocked by risk filter: %s", risk_check["reasons"])
                signal_type = "NO TRADE"
                trade_plan["risk_block_reasons"] = risk_check["reasons"]

        reasoning = self._build_reasoning(
            signal_type=signal_type,
            tech=tech,
            smc_score=smc_score,
            ml_score=ml_score,
            news_score=news_score,
            economic_score=economic_score,
            composite=composite,
        )

        return {
            "signal_type": signal_type,
            "direction": direction,
            "composite_score": round(composite, 1),
            "confidence": round(confidence, 1),
            "technical_score": round(tech_score, 1),
            "smc_score": round(smc_val, 1),
            "ml_score": round(ml_val, 1),
            "news_score": round(news_val, 1),
            "economic_score": round(econ_val, 1),
            "entry": trade_plan.get("entry"),
            "stop_loss": trade_plan.get("stop_loss"),
            "take_profit": trade_plan.get("take_profit_1"),
            "risk_reward": trade_plan.get("risk_reward"),
            "lot_size": trade_plan.get("lot_size"),
            "trade_plan": trade_plan,
            "reasoning": reasoning,
            "timestamp": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _build_reasoning(
        signal_type: str,
        tech: Dict[str, Any],
        smc_score: Optional[Dict[str, Any]],
        ml_score: Optional[Dict[str, Any]],
        news_score: Optional[Dict[str, Any]],
        economic_score: Optional[Dict[str, Any]],
        composite: float,
    ) -> str:
        lines = [f"Signal: {signal_type} | Composite Score: {composite:.1f}/100"]
        lines.append(f"Technical ({tech['score']:.1f}): {tech['direction'].upper()} — {', '.join(tech.get('details', {}).get('patterns', []) or ['no patterns'])}")
        if smc_score:
            lines.append(f"SMC ({smc_score.get('score', 50):.1f}): {smc_score.get('direction', 'neutral').upper()} — {smc_score.get('events', 0)} events detected")
        if ml_score:
            lines.append(f"ML ({ml_score.get('score', 50):.1f}): {ml_score.get('direction', 'neutral').upper()} prediction")
        if news_score:
            lines.append(f"News ({news_score.get('score', 50):.1f}): {news_score.get('direction', 'neutral').upper()} — {news_score.get('article_count', 0)} articles")
        if economic_score:
            lines.append(f"Economic ({economic_score.get('score', 50):.1f}): {economic_score.get('direction', 'neutral').upper()} — avg impact {economic_score.get('avg_impact', 5):.1f}/10")
        return " | ".join(lines)


signal_scorer = SignalScorer()
