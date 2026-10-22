"""
Gold_AI v2 signal strategy — pure, DB-free, testable.

Modules:
  config        StrategyConfig / RiskConfig (env-overridable parameters)
  data_quality  candle cleaning + validation (forming bar, weekend filler,
                contamination, staleness, gaps)
  indicators    causal numpy indicator series (EMA, Wilder ATR/RSI/ADX)
  engine        regime detection + BUY/SELL/NO TRADE decision
  backtest      cost-aware, bar-by-bar simulator + metrics

The engine never places orders. It only produces signal decisions.
"""

STRATEGY_VERSION = "v2.0.0"
