# Gold AI — API Reference

Base URL: `http://localhost/api/v1` (via Nginx) or `http://localhost:8001/api/v1` (direct)

Interactive docs: `http://localhost/api/docs` (Swagger UI)

## Authentication

All protected endpoints require:
```
Authorization: Bearer <access_token>
```

### Register
`POST /auth/register`
```json
{ "email": "user@example.com", "password": "StrongPass123!" }
```

### Login
`POST /auth/login`
```json
{ "email": "user@example.com", "password": "StrongPass123!" }
```
Response:
```json
{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }
```

### Refresh
`POST /auth/refresh`

Header: `Authorization: Bearer <refresh_token>`

### Logout
`POST /auth/logout`

Blacklists the current access token in Redis.

---

## Market Data

### Current price
`GET /market-data/price?symbol=XAUUSD`

### OHLCV candles
`GET /market-data/candles?symbol=XAUUSD&timeframe=60&limit=200`

### Historical ingest
`POST /market-data/ingest` *(admin)*

---

## Indicators

### Snapshot (all indicators)
`GET /indicators/snapshot?symbol=XAUUSD&timeframe=60`

Response includes: `rsi`, `macd`, `macd_signal`, `ema_20`, `ema_50`, `ema_200`, `bb_upper`, `bb_lower`, `atr`.

---

## SMC Analysis

### SMC score
`GET /smc/score?symbol=XAUUSD&timeframe=60`

```json
{
  "direction": "bullish",
  "score": 68.5,
  "components": {
    "order_block": 75,
    "fvg": 60,
    "bos": 70
  }
}
```

---

## Signals

### Generate signal
`POST /signals/generate`
```json
{ "symbol": "XAUUSD", "timeframe": "60" }
```

Response:
```json
{
  "signal_type": "BUY",
  "confidence": 74.2,
  "combined_score": 74.2,
  "entry": 2315.50,
  "stop_loss": 2300.00,
  "take_profit": 2345.00,
  "rr": 1.97,
  "technical_score": 78,
  "smc_score": 71,
  "ml_score": 68,
  "news_score": 60,
  "reasoning": "Strong bullish confluence..."
}
```

### Signal history
`GET /signals?symbol=XAUUSD&timeframe=60&limit=50`

---

## ML

### Train model
`POST /ml/train`
```json
{ "symbol": "XAUUSD", "timeframe": "60" }
```

### Predict
`POST /ml/predict`
```json
{ "symbol": "XAUUSD", "timeframe": "60" }
```

### Feedback accuracy
`GET /ml/feedback/accuracy?symbol=XAUUSD&timeframe=60&last_n=100`

### Error patterns
`GET /ml/feedback/error-patterns?symbol=XAUUSD&timeframe=60&min_occurrences=2`

### Manual retrain
`POST /ml/feedback/retrain?symbol=XAUUSD&timeframe=60`

---

## Risk Management

### Risk status
`GET /risk/status?account_id=default&balance=10000`

```json
{
  "account_id": "default",
  "open_trades": 2,
  "daily_pnl": -45.00,
  "daily_loss_pct": 0.45,
  "weekly_pnl": 120.00,
  "weekly_loss_pct": -1.2,
  "can_trade": true
}
```

### Can trade check
`GET /risk/can-trade?account_id=default&balance=10000&symbol=XAUUSD`

```json
{
  "allowed": true,
  "reasons": []
}
```

Blocked example:
```json
{
  "allowed": false,
  "reasons": ["Daily loss limit reached (3.0%)"]
}
```

---

## Forecast

`GET /forecast?symbol=XAUUSD&timeframe=60`

```json
{
  "direction": "bullish",
  "confidence": 67.0,
  "current_price": 2318.40,
  "target_1": 2340.00,
  "target_2": 2360.00,
  "stop_loss": 2298.00,
  "regime": "TRENDING_UP",
  "summary": "Strong uptrend with bullish SMC confluence"
}
```

---

## News

`GET /news?limit=10&sentiment=bullish`

---

## Economic Calendar

`GET /economic-calendar?impact=high&days_ahead=3`

---

## Backtesting

`POST /backtesting/run`
```json
{
  "symbol": "XAUUSD",
  "timeframe": "60",
  "start_date": "2024-01-01",
  "end_date": "2024-06-01"
}
```

---

## Admin

All admin endpoints require `is_admin=True` on the user.

`GET /admin/users` — List all users
`DELETE /admin/users/{id}` — Delete user
`POST /admin/logs` — System logs

---

## Health & Metrics

`GET /api/v1/health` — Service health
`GET /metrics` — Prometheus metrics (Prometheus format)

---

## Error Responses

All errors follow:
```json
{ "detail": "Human-readable error message" }
```

| Code | Meaning                          |
|------|----------------------------------|
| 400  | Bad request / validation error   |
| 401  | Missing or invalid token         |
| 403  | Forbidden (not admin)            |
| 404  | Resource not found               |
| 422  | Unprocessable entity (Pydantic)  |
| 429  | Rate limit exceeded              |
| 500  | Internal server error            |
