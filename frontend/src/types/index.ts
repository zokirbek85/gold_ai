export interface Candle {
  id: number;
  symbol: string;
  timeframe: string;
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Signal {
  id: number;
  symbol: string;
  timeframe: string;
  signal_type: "BUY" | "SELL" | "NO TRADE";
  entry: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  rr: number | null;
  confidence: number | null;
  technical_score: number | null;
  smc_score: number | null;
  ml_score: number | null;
  news_score: number | null;
  economic_score: number | null;
  reasoning: string | null;
  created_at: string;
}

export interface NewsArticle {
  id: number;
  source: string;
  title: string;
  url: string;
  published_at: string;
  summary: string | null;
  impact_score: number | null;
  confidence: number | null;
  duration: string | null;
}

export interface EconomicEvent {
  id: number;
  provider: string;
  event_type: string;
  country: string;
  scheduled_at: string;
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  surprise: number | null;
  impact: number | null;
}

export interface IndicatorSnapshot {
  EMA_20?: number;
  EMA_50?: number;
  EMA_100?: number;
  EMA_200?: number;
  RSI_14?: number;
  MACD_line?: number;
  MACD_signal?: number;
  MACD_hist?: number;
  STOCH_K?: number;
  STOCH_D?: number;
  ATR_14?: number;
  BB_upper?: number;
  BB_middle?: number;
  BB_lower?: number;
  VWAP?: number;
  OBV?: number;
  ADX?: number;
  PLUS_DI?: number;
  MINUS_DI?: number;
}

export interface Pattern {
  name: string;
  direction: "bullish" | "bearish" | "neutral";
  confidence: number;
  description: string;
  extra?: Record<string, unknown>;
}

export interface SMCAnalysis {
  market_structure: Array<{ type: string; direction: string; broken_level: number; description: string }>;
  order_blocks: Array<{ type: string; ob_high: number; ob_low: number; direction: string }>;
  fair_value_gaps: Array<{ type: string; fvg_high: number; fvg_low: number; direction: string }>;
  premium_discount: { zone: string; pct_of_range: number; equilibrium: number; swing_high: number; swing_low: number };
}

export interface MLPrediction {
  buy_pct: number;
  sell_pct: number;
  neutral_pct: number;
  direction: string;
  score: number;
  models_used: number;
}

export interface BacktestResult {
  id: number;
  name: string;
  metrics: {
    total_trades: number;
    win_rate: number;
    profit_factor: number;
    sharpe_ratio: number;
    max_drawdown_pct: number;
    total_pnl: number;
    avg_rr: number;
    monthly_returns: Record<string, number>;
  };
}
