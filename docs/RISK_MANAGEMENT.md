# Gold AI — Risk Management

## Overview

Risk management operates at two levels: **trade-level** (position sizing, R:R filter) and **session-level** (daily/weekly loss limits, max open trades, correlation limits).

## Trade-Level Risk (`src/risk_management/calculator.py`)

### Position Sizing

Formula: `lots = risk_amount / (sl_pips × pip_value)`

Where:
- `risk_amount = account_balance × RISK_PCT` (default 1%)
- `sl_pips = abs(entry - stop_loss) / pip_size`
- `pip_value` = instrument-specific (100 for XAUUSD/USD, 10 for most pairs)

Minimum lot: 0.01. If SL = 0 or calculation returns 0, position size is 0 (no trade).

### Take-Profit Targets

Three targets generated at fixed R:R multiples:

| Target | R:R   | Partial Close |
|--------|-------|---------------|
| TP1    | 1.5R  | 30%           |
| TP2    | 2.0R  | 40%           |
| TP3    | 3.0R  | 30%           |

Directions:
- BUY: `target = entry + (sl_distance × rr_multiple)`
- SELL: `target = entry - (sl_distance × rr_multiple)`

### Risk Filter

A trade plan must pass all checks before execution:

| Check                    | Threshold       | Reason if fails    |
|--------------------------|-----------------|--------------------|
| R:R ratio                | ≥ 1.5           | "R:R below 1.5"    |
| Lot size                 | > 0             | "Invalid lot size" |
| Take-profit > entry (BUY)| TP1 > entry     | "Invalid TP"       |

### ATR Calculation

14-period ATR using true range: `TR = max(H-L, |H-prev_close|, |prev_close-L|)`

## Session-Level Risk (`backend/core/risk_tracker.py`)

All counters stored in Redis with TTL-based automatic reset:
- Daily counters: `86400s` TTL
- Weekly counters: `604800s` TTL

### Limits

| Limit                | Default | Redis Key Pattern           |
|----------------------|---------|-----------------------------|
| Max daily loss       | 3%      | `risk:{acct}:daily_pnl`    |
| Max weekly loss      | 6%      | `risk:{acct}:weekly_pnl`   |
| Max open trades      | 5       | `risk:{acct}:open_trades`  |
| Max correlated trades| 2       | `risk:{acct}:corr:{group}` |

### Correlation Groups

| Group      | Symbols                               |
|------------|---------------------------------------|
| metals     | XAUUSD, XAGUSD, XPTUSD               |
| usd_majors | EURUSD, GBPUSD, AUDUSD, NZDUSD       |
| jpy        | USDJPY, EURJPY, GBPJPY               |

### `can_trade()` Logic

Returns `{allowed: bool, reasons: []}`. Fails when:
1. `daily_pnl < -balance × MAX_DAILY_LOSS_PCT`
2. `weekly_pnl < -balance × MAX_WEEKLY_LOSS_PCT`
3. `open_trades >= MAX_OPEN_TRADES`
4. `correlated_count[group] >= MAX_CORRELATED_TRADES`

Degrades gracefully: if Redis is unavailable, all checks pass (fail-open, no blocking).

### Recording Trades

```python
tracker = get_risk_tracker()

# When a trade opens
tracker.record_trade_opened(account_id, symbol)

# When P&L is realized
tracker.record_trade_pnl(account_id, pnl_amount)

# When a trade closes
tracker.record_trade_closed(account_id, symbol)
```

## API Endpoints

`GET /api/v1/risk/status?account_id=default&balance=10000`
`GET /api/v1/risk/can-trade?account_id=default&balance=10000&symbol=XAUUSD`

## Configuration

Override defaults via environment variables (if added to `Settings`):

```env
MAX_DAILY_LOSS_PCT=0.03
MAX_WEEKLY_LOSS_PCT=0.06
MAX_OPEN_TRADES=5
MAX_CORRELATED_TRADES=2
```
