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
        """Score 0–100. >50 = bullish, <50 = bearish. Also returns human-readable bullets."""
        if len(candles) < 20:
            return {"score": 50.0, "direction": "neutral", "details": {}, "bullets": ["Insufficient candle data for technical analysis"]}

        indicators = ind_calc.compute_all(candles)
        close = float(candles[-1]["close"])

        bull_signals = 0
        bear_signals = 0
        total_signals = 0
        bullets: List[str] = []

        # EMA trend alignment
        for period_key in ["EMA_20", "EMA_50", "EMA_100", "EMA_200"]:
            val = indicators.get(period_key)
            if val is not None:
                period = period_key.split("_")[1]
                total_signals += 1
                if close > val:
                    bull_signals += 1
                    bullets.append(f"Price above EMA {period} ({val:.0f}) — uptrend")
                else:
                    bear_signals += 1
                    bullets.append(f"Price below EMA {period} ({val:.0f}) — bearish")

        # RSI
        rsi = indicators.get("RSI_14")
        if rsi is not None:
            total_signals += 1
            if rsi < 30:
                bull_signals += 2
                total_signals += 1
                bullets.append(f"RSI {rsi:.0f} — oversold zone, reversal expected")
            elif rsi > 70:
                bear_signals += 2
                total_signals += 1
                bullets.append(f"RSI {rsi:.0f} — overbought zone, pullback likely")
            elif 40 < rsi < 60:
                bullets.append(f"RSI {rsi:.0f} — neutral range")
            elif rsi > 55:
                bull_signals += 1
                bullets.append(f"RSI {rsi:.0f} — mild bullish momentum")
            else:
                bear_signals += 1
                bullets.append(f"RSI {rsi:.0f} — mild bearish momentum")

        # MACD
        macd_line = indicators.get("MACD_line")
        macd_sig = indicators.get("MACD_signal")
        if macd_line is not None and macd_sig is not None:
            total_signals += 1
            if macd_line > macd_sig:
                bull_signals += 1
                bullets.append("MACD above signal line — momentum rising")
            else:
                bear_signals += 1
                bullets.append("MACD below signal line — momentum falling")

        # Stochastic
        k = indicators.get("STOCH_K")
        if k is not None:
            total_signals += 1
            if k < 20:
                bull_signals += 1
                bullets.append(f"Stochastic K {k:.0f} — oversold, bounce possible")
            elif k > 80:
                bear_signals += 1
                bullets.append(f"Stochastic K {k:.0f} — overbought, reversal risk")
            else:
                bullets.append(f"Stochastic K {k:.0f} — neutral zone")

        # ADX
        adx = indicators.get("ADX")
        plus_di = indicators.get("PLUS_DI")
        minus_di = indicators.get("MINUS_DI")
        if adx and adx > 25 and plus_di is not None and minus_di is not None:
            total_signals += 1
            if plus_di > minus_di:
                bull_signals += 1
                bullets.append(f"Strong trend (ADX {adx:.0f}) — +DI > -DI, bullish pressure")
            else:
                bear_signals += 1
                bullets.append(f"Strong trend (ADX {adx:.0f}) — -DI > +DI, bearish pressure")

        # Bollinger Band position
        bb_upper = indicators.get("BB_upper")
        bb_lower = indicators.get("BB_lower")
        if bb_upper and bb_lower:
            total_signals += 1
            if close < bb_lower:
                bull_signals += 1
                bullets.append(f"Price below Bollinger lower band ({bb_lower:.0f}) — oversold reversal zone")
            elif close > bb_upper:
                bear_signals += 1
                bullets.append(f"Price above Bollinger upper band ({bb_upper:.0f}) — overbought reversal zone")
            else:
                bullets.append("Price inside Bollinger Bands — no breakout signal")

        # Pattern bonus
        candlestick_patterns = candlestick_detector.detect_all(candles[-5:])
        chart_patterns = chart_detector.detect_all(candles)
        for p in candlestick_patterns + chart_patterns:
            total_signals += 1
            name = p.get("name", "Pattern").replace("_", " ").capitalize()
            if p["direction"] == "bullish":
                bull_signals += p.get("confidence", 0.5)
                bullets.append(f"{name} pattern — bullish signal")
            elif p["direction"] == "bearish":
                bear_signals += p.get("confidence", 0.5)
                bullets.append(f"{name} pattern — bearish signal")

        total_weight = bull_signals + bear_signals
        if total_weight == 0 or total_signals == 0:
            score = 50.0
            direction = "neutral"
        else:
            score = bull_signals / total_weight * 100
            direction = "bullish" if score > 55 else ("bearish" if score < 45 else "neutral")

        if not bullets:
            bullets.append("No clear technical signals detected")

        return {
            "score": round(score, 1),
            "direction": direction,
            "bullets": bullets,
            "details": {
                "indicators": {k: v for k, v in indicators.items() if v is not None},
                "patterns": [p["name"] for p in candlestick_patterns + chart_patterns],
            },
        }

    def confluence_score(
        self,
        candles_h4: List[Dict[str, Any]],
        candles_h1: List[Dict[str, Any]],
        candles_m15: List[Dict[str, Any]],
        primary_direction: str,
    ) -> Dict[str, Any]:
        """
        Multi-timeframe confluence scoring using EMA 20 vs EMA 50 crossover.

        H4 = trend direction (biggest weight)
        H1 = signal direction
        M15 = entry trigger (smallest weight)

        Returns:
            score      : float 0-100 (bonus to blend into composite)
            alignment  : "full" | "partial" | "conflict"
            details    : per-timeframe directions
        """
        def _ema_direction(candles: List[Dict[str, Any]]) -> str:
            if len(candles) < 50:
                return "neutral"
            ema20 = ind_calc.ema(candles, 20)
            ema50 = ind_calc.ema(candles, 50)
            if ema20 is None or ema50 is None:
                return "neutral"
            if ema20 > ema50:
                return "bullish"
            if ema20 < ema50:
                return "bearish"
            return "neutral"

        h4_dir  = _ema_direction(candles_h4)
        h1_dir  = _ema_direction(candles_h1)
        m15_dir = _ema_direction(candles_m15)

        score = 50.0

        # H4 is the most consequential timeframe
        if h4_dir == primary_direction:
            score += 15
        elif h4_dir != "neutral":        # h4 explicitly opposes primary direction
            score -= 20

        if h1_dir == primary_direction:
            score += 10

        if m15_dir == primary_direction:
            score += 5

        score = max(0.0, min(100.0, score))

        # Alignment label
        h4_conflicts = h4_dir != "neutral" and h4_dir != primary_direction
        all_agree = (h4_dir == h1_dir == m15_dir == primary_direction)
        if h4_conflicts:
            alignment = "conflict"
        elif all_agree:
            alignment = "full"
        else:
            alignment = "partial"

        return {
            "score": round(score, 1),
            "alignment": alignment,
            "details": {
                "h4_direction": h4_dir,
                "h1_direction": h1_dir,
                "m15_direction": m15_dir,
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
        candles_h4: Optional[List[Dict[str, Any]]] = None,
        candles_h1: Optional[List[Dict[str, Any]]] = None,
        candles_m15: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a trading signal by combining all score layers.
        Each score dict: {"direction": "bullish"|"bearish"|"neutral", "score": float 0-100}

        Optional multi-timeframe candles trigger confluence scoring when all three
        (candles_h4, candles_h1, candles_m15) are provided.
        """
        tech = self._technical_score(candles)

        def _normalize(score_dict: Optional[Dict[str, Any]]) -> float:
            if not score_dict:
                return 50.0
            return float(score_dict.get("score", 50.0))

        tech_score = _normalize(tech)
        smc_val    = _normalize(smc_score)
        ml_val     = _normalize(ml_score)
        news_val   = _normalize(news_score)
        econ_val   = _normalize(economic_score)

        # Weighted composite score (>50 bullish, <50 bearish)
        composite: float = (
            tech_score * WEIGHTS["technical"]
            + smc_val  * WEIGHTS["smc"]
            + ml_val   * WEIGHTS["ml"]
            + news_val * WEIGHTS["news"]
            + econ_val * WEIGHTS["economic"]
        )

        # Initial signal determination (needed as input to confluence_score)
        if composite >= SIGNAL_THRESHOLD_BUY:
            signal_type = "BUY"
            direction   = "bullish"
        elif composite <= SIGNAL_THRESHOLD_SELL:
            signal_type = "SELL"
            direction   = "bearish"
        else:
            signal_type = "NO TRADE"
            direction   = "neutral"

        # ── Multi-timeframe confluence ──────────────────────────────────────
        confluence: Optional[Dict[str, Any]] = None
        if candles_h4 is not None and candles_h1 is not None and candles_m15 is not None:
            # Use a concrete direction for scoring even when composite is neutral
            conf_dir = direction if direction != "neutral" else (
                "bullish" if composite > 50 else "bearish"
            )
            confluence = self.confluence_score(candles_h4, candles_h1, candles_m15, conf_dir)
            alignment  = confluence["alignment"]

            if alignment == "full":
                composite = min(100.0, composite + 8)
            elif alignment == "partial":
                composite = min(100.0, composite + 3)
            else:  # conflict
                composite = max(0.0, composite - 10)

            # Re-evaluate signal from adjusted composite
            if alignment == "conflict" and composite < 70:
                # H4 opposition requires high conviction — tighten threshold
                signal_type = "NO TRADE"
                direction   = "neutral"
            elif composite >= SIGNAL_THRESHOLD_BUY:
                signal_type = "BUY"
                direction   = "bullish"
            elif composite <= SIGNAL_THRESHOLD_SELL:
                signal_type = "SELL"
                direction   = "bearish"
            else:
                signal_type = "NO TRADE"
                direction   = "neutral"

        confidence = abs(composite - 50) * 2  # 0–100

        trade_plan: Dict[str, Any] = {}
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

        reasoning_structured = self._build_structured_reasoning(
            signal_type=signal_type,
            direction=direction,
            tech=tech,
            smc_score=smc_score,
            ml_score=ml_score,
            news_score=news_score,
            economic_score=economic_score,
            composite=composite,
            trade_plan=trade_plan,
            account_balance=account_balance,
        )

        return {
            "signal_type":        signal_type,
            "direction":          direction,
            "composite_score":    round(composite, 1),
            "confidence":         round(confidence, 1),
            "technical_score":    round(tech_score, 1),
            "smc_score":          round(smc_val, 1),
            "ml_score":           round(ml_val, 1),
            "news_score":         round(news_val, 1),
            "economic_score":     round(econ_val, 1),
            "entry":              trade_plan.get("entry"),
            "stop_loss":          trade_plan.get("stop_loss"),
            "take_profit":        trade_plan.get("take_profit_1"),
            "risk_reward":        trade_plan.get("risk_reward"),
            "lot_size":           trade_plan.get("lot_size"),
            "trade_plan":         trade_plan,
            "confluence":         confluence,
            "reasoning":          reasoning,
            "reasoning_structured": reasoning_structured,
            "timestamp":          datetime.utcnow().isoformat(),
        }

    def _build_structured_reasoning(
        self,
        signal_type: str,
        direction: str,
        tech: Dict[str, Any],
        smc_score: Optional[Dict[str, Any]],
        ml_score: Optional[Dict[str, Any]],
        news_score: Optional[Dict[str, Any]],
        economic_score: Optional[Dict[str, Any]],
        composite: float,
        trade_plan: Dict[str, Any],
        account_balance: float = 10000.0,
    ) -> Dict[str, Any]:
        """Build a structured reasoning dict parseable by the frontend."""

        def _layer_status(layer_dir: str) -> str:
            if direction == "neutral" or layer_dir == "neutral":
                return "neutral"
            return "confirm" if layer_dir == direction else "conflict"

        def _dir(score_dict: Optional[Dict[str, Any]], fallback: str = "neutral") -> str:
            if not score_dict:
                return fallback
            return score_dict.get("direction", fallback)

        def _score(score_dict: Optional[Dict[str, Any]]) -> float:
            if not score_dict:
                return 50.0
            return float(score_dict.get("score", 50.0))

        # ── Technical layer ──────────────────────────────────────────
        tech_dir = tech.get("direction", "neutral")
        tech_layer: Dict[str, Any] = {
            "name":      "Technical analysis",
            "score":     tech["score"],
            "direction": tech_dir,
            "status":    _layer_status(tech_dir),
            "bullets":   tech.get("bullets", []),
        }

        # ── SMC layer ────────────────────────────────────────────────
        smc_dir = _dir(smc_score)
        smc_bullets: List[str] = []
        if smc_score:
            events = smc_score.get("events", 0)
            if smc_dir == "bullish":
                smc_bullets.append("Bullish market structure confirmed")
            elif smc_dir == "bearish":
                smc_bullets.append("Bearish market structure confirmed")
            else:
                smc_bullets.append("No clear SMC structure detected")
            if events:
                smc_bullets.append(f"{events} SMC events detected (BOS / CHOCH / OB)")
            details = smc_score.get("details") or {}
            if details.get("order_blocks"):
                smc_bullets.append(f"Order block zone identified near {details['order_blocks']}")
            if details.get("bos"):
                smc_bullets.append("Break of Structure (BOS) signal present")
            if details.get("fvg"):
                smc_bullets.append("Fair Value Gap (FVG) detected")
        else:
            smc_bullets.append("No SMC analysis provided")
        smc_layer: Dict[str, Any] = {
            "name":      "Smart Money (SMC)",
            "score":     _score(smc_score),
            "direction": smc_dir,
            "status":    _layer_status(smc_dir),
            "bullets":   smc_bullets,
        }

        # ── ML layer ─────────────────────────────────────────────────
        ml_dir = _dir(ml_score)
        ml_bullets: List[str] = []
        if ml_score:
            ml_conf = ml_score.get("confidence", abs(_score(ml_score) - 50) * 2)
            ml_bullets.append(f"Model predicts {ml_dir} move ({ml_conf:.0f}% confidence)")
            buy_pct  = ml_score.get("buy_pct")
            sell_pct = ml_score.get("sell_pct")
            if buy_pct is not None and sell_pct is not None:
                ml_bullets.append(f"Buy probability: {buy_pct:.0f}% | Sell probability: {sell_pct:.0f}%")
            models_used = ml_score.get("models_used")
            if models_used:
                ml_bullets.append(f"{models_used} model(s) used in ensemble")
        else:
            ml_bullets.append("No ML model available for this instrument")
        ml_layer: Dict[str, Any] = {
            "name":      "Machine learning",
            "score":     _score(ml_score),
            "direction": ml_dir,
            "status":    _layer_status(ml_dir),
            "bullets":   ml_bullets,
        }

        # ── News layer ───────────────────────────────────────────────
        news_dir = _dir(news_score)
        news_bullets: List[str] = []
        if news_score:
            article_count = news_score.get("article_count", 0)
            hours = news_score.get("hours", 4)
            if article_count:
                news_bullets.append(f"{article_count} article(s) analysed in the last {hours}h — {news_dir} sentiment")
            else:
                news_bullets.append(f"No major gold news in the last {hours} hours")
            headline = news_score.get("top_headline")
            if headline:
                news_bullets.append(f"Top headline: {headline}")
        else:
            news_bullets.append("No news sentiment data available")
        news_layer: Dict[str, Any] = {
            "name":      "News & sentiment",
            "score":     _score(news_score),
            "direction": news_dir,
            "status":    _layer_status(news_dir),
            "bullets":   news_bullets,
        }

        # ── Economic layer ───────────────────────────────────────────
        econ_dir = _dir(economic_score)
        econ_bullets: List[str] = []
        if economic_score:
            event_count = economic_score.get("event_count", 0)
            avg_impact  = economic_score.get("avg_impact", 0.0)
            if event_count:
                econ_bullets.append(f"{event_count} economic event(s) — average impact {avg_impact:.1f}/10")
            else:
                econ_bullets.append("No high-impact economic events scheduled")
            if econ_dir != "neutral":
                econ_bullets.append(f"Economic outlook leans {econ_dir}")
        else:
            econ_bullets.append("No economic calendar data available")
        econ_layer: Dict[str, Any] = {
            "name":      "Economic calendar",
            "score":     _score(economic_score),
            "direction": econ_dir,
            "status":    _layer_status(econ_dir),
            "bullets":   econ_bullets,
        }

        layers = [tech_layer, smc_layer, ml_layer, news_layer, econ_layer]

        # ── Summary ──────────────────────────────────────────────────
        confirming = sum(1 for l in layers if l["status"] == "confirm")
        summary = f"{confirming} out of {len(layers)} layers agree: {signal_type}"

        # ── Risk summary ─────────────────────────────────────────────
        risk_amount = trade_plan.get("risk_amount_usd", account_balance * 0.01)
        rr = trade_plan.get("risk_reward") or 0.0
        if trade_plan and rr:
            target = risk_amount * rr
            risk_summary = (
                f"Risk: ${risk_amount:.0f} (1% of account) | "
                f"Target: ${target:.0f} (1:{rr:.1f} RR)"
            )
        else:
            risk_summary = "Risk parameters not available — signal is NO TRADE"

        # ── Caution: any high-weight layer conflicts with final direction ──
        caution: Optional[str] = None
        high_weight_layers = [
            (tech_layer, WEIGHTS["technical"]),
            (smc_layer,  WEIGHTS["smc"]),
            (ml_layer,   WEIGHTS["ml"]),
        ]
        for layer, weight in high_weight_layers:
            if weight >= 0.20 and layer["status"] == "conflict":
                caution = "Conflicting signals detected — consider waiting for confirmation"
                break

        return {
            "summary":      summary,
            "layers":       layers,
            "risk_summary": risk_summary,
            "caution":      caution,
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
