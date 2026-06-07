"""
Risk Management calculator.
- ATR-based dynamic stop loss
- Position sizing (max 1% account risk)
- Minimum 1:2 Risk/Reward enforcement
- Pre-signal risk filters

XAUUSD lot-size example:
    # Account: $10,000 | Entry: 2300.00 | SL: 2285.00 | Risk: 1%
    # SL distance: 15.00 | Risk $: $100 | Lot size: ~0.07 lots
    #
    # pip_value (XAUUSD) = $1.00/lot/pip  (1 lot = 100 oz, pip = $0.01)
    # sl_pips  = 15.00 / 1.0  = 15
    # lot_size = $100 / (15 * 1.0 * 100) = 0.0667 ≈ 0.07
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class RiskCalculator:
    MAX_RISK_PCT: float = 0.01       # 1% of account per trade
    MIN_RR: float = 2.0              # Minimum Risk:Reward
    ATR_MULTIPLIER: float = 1.5      # SL = entry ± ATR * multiplier

    # Dollar value of 1 pip movement for 1 standard lot.
    # XAUUSD : 1 lot = 100 oz, pip = $0.01  → $1.00/lot/pip
    # EURUSD  : 1 lot = 100k units, pip = $0.0001 → $10.00/lot/pip
    PIP_VALUES: Dict[str, float] = {
        "XAUUSD": 1.0,
        "EURUSD": 10.0,
        "GBPUSD": 10.0,
        "USDJPY": 9.09,
    }
    DEFAULT_PIP_VALUE: float = 10.0

    def calculate_atr(self, candles: List[Dict[str, Any]], period: int = 14) -> Optional[float]:
        if len(candles) < period + 1:
            return None
        trs = []
        for i in range(1, len(candles)):
            hl = float(candles[i]["high"]) - float(candles[i]["low"])
            hc = abs(float(candles[i]["high"]) - float(candles[i - 1]["close"]))
            lc = abs(float(candles[i]["low"]) - float(candles[i - 1]["close"]))
            trs.append(max(hl, hc, lc))
        if len(trs) < period:
            return None
        atr = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr = (atr * (period - 1) + tr) / period
        return atr

    def position_size(
        self,
        account_balance: float,
        entry: float,
        stop_loss: float,
        symbol: str = "XAUUSD",
        pip_value: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Calculate lot size so that risk = MAX_RISK_PCT of account balance.

        Formula: lot_size = risk_$ / (sl_pips * pip_value * 100)
        where sl_pips = sl_distance / pip_value.
        """
        if pip_value is None:
            pip_value = self.PIP_VALUES.get(symbol, self.DEFAULT_PIP_VALUE)

        risk_amount = account_balance * self.MAX_RISK_PCT
        sl_distance = abs(entry - stop_loss)
        if sl_distance == 0:
            return {"lots": 0.0, "risk_amount": 0.0, "sl_pips": 0.0}

        sl_pips = sl_distance / pip_value
        lot_size = risk_amount / (sl_pips * pip_value * 100)
        return {
            "lots": round(max(0.01, lot_size), 2),
            "risk_amount": round(risk_amount, 2),
            "sl_pips": round(sl_pips, 1),
        }

    def calculate_targets(
        self,
        entry: float,
        stop_loss: float,
        direction: str,
        rr_ratios: List[float] = None,
    ) -> List[Dict[str, Any]]:
        """Calculate TP levels for given R:R ratios."""
        if rr_ratios is None:
            rr_ratios = [2.0, 3.0, 5.0]
        sl_dist = abs(entry - stop_loss)
        targets = []
        for rr in rr_ratios:
            if direction == "bullish":
                tp = entry + sl_dist * rr
            else:
                tp = entry - sl_dist * rr
            targets.append({"rr": rr, "price": round(tp, 5)})
        return targets

    def build_trade_plan(
        self,
        candles: List[Dict[str, Any]],
        direction: str,
        account_balance: float = 10000.0,
        atr_multiplier: float = None,
        symbol: str = "XAUUSD",
    ) -> Dict[str, Any]:
        """
        Full trade plan: entry, SL (ATR-based), TP (1:2, 1:3), position size.
        direction: 'bullish' | 'bearish'
        """
        if not candles:
            return {}
        atr_mult = atr_multiplier or self.ATR_MULTIPLIER
        atr = self.calculate_atr(candles)
        entry = float(candles[-1]["close"])
        if atr is None:
            atr = abs(float(candles[-1]["high"]) - float(candles[-1]["low"]))

        if direction == "bullish":
            stop_loss = entry - atr * atr_mult
            take_profit_1 = entry + atr * atr_mult * 2
            take_profit_2 = entry + atr * atr_mult * 3
        else:
            stop_loss = entry + atr * atr_mult
            take_profit_1 = entry - atr * atr_mult * 2
            take_profit_2 = entry - atr * atr_mult * 3

        sl_distance = abs(entry - stop_loss)
        rr = abs(take_profit_1 - entry) / sl_distance if sl_distance > 0 else 0

        sizing = self.position_size(account_balance, entry, stop_loss, symbol=symbol)
        targets = self.calculate_targets(entry, stop_loss, direction)

        plan = {
            "direction": direction,
            "symbol": symbol,
            "entry": round(entry, 5),
            "stop_loss": round(stop_loss, 5),
            "take_profit_1": round(take_profit_1, 5),
            "take_profit_2": round(take_profit_2, 5),
            "atr": round(atr, 5),
            "risk_reward": round(rr, 2),
            "lot_size": sizing["lots"],
            "risk_amount_usd": sizing["risk_amount"],
            "sl_pips": sizing["sl_pips"],
            "targets": targets,
        }
        return plan

    def validate_trade_plan(self, trade_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Sanity-check lot size and key fields; logs a warning for oversized positions."""
        warnings: List[str] = []
        lot_size = trade_plan.get("lot_size", 0)
        if lot_size > 10.0:
            msg = f"Oversized position: lot_size={lot_size} exceeds 10.0 — check account balance and SL distance"
            log.warning(msg)
            warnings.append(msg)
        if lot_size <= 0:
            warnings.append("lot_size is zero or negative")
        return {"valid": len(warnings) == 0, "warnings": warnings}

    def passes_risk_filter(self, trade_plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate trade plan against risk rules.
        Returns: {"passed": bool, "reasons": List[str]}
        """
        reasons: List[str] = []
        rr = trade_plan.get("risk_reward", 0)
        if rr < self.MIN_RR:
            reasons.append(f"R:R {rr:.2f} below minimum {self.MIN_RR}")
        if trade_plan.get("lot_size", 0) <= 0:
            reasons.append("Invalid lot size")
        if trade_plan.get("entry", 0) == trade_plan.get("stop_loss", 0):
            reasons.append("Entry equals stop loss")
        return {"passed": len(reasons) == 0, "reasons": reasons}


risk_calculator = RiskCalculator()
