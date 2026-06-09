# Gold AI — Database Review

## Schema Overview

PostgreSQL 16. All tables use `Integer` primary keys with auto-increment.

### `users`
| Column        | Type         | Notes                          |
|---------------|--------------|--------------------------------|
| id            | Integer PK   |                                |
| email         | String(255)  | UNIQUE, NOT NULL, indexed      |
| password_hash | String(255)  | PBKDF2-SHA256                  |
| is_active     | Boolean      | Default True                   |
| is_admin      | Boolean      | Default False                  |
| created_at    | DateTime     | UTC, auto-set                  |
| updated_at    | DateTime     | UTC, auto-updated on change    |
| last_login    | DateTime     | Nullable                       |

### `candles`
| Column    | Type        | Notes                                    |
|-----------|-------------|------------------------------------------|
| id        | Integer PK  |                                          |
| symbol    | String(20)  | e.g. "XAUUSD"                           |
| timeframe | String(10)  | e.g. "60" (minutes)                     |
| timestamp | DateTime    | UTC                                      |
| open      | Float       |                                          |
| high      | Float       |                                          |
| low       | Float       |                                          |
| close     | Float       |                                          |
| volume    | Float       |                                          |

**Constraints:**
- `UNIQUE (symbol, timeframe, timestamp)` — prevents duplicates
- `INDEX (symbol, timeframe, timestamp)` — fast range queries
- `INDEX (symbol, timeframe, timestamp DESC)` — fast "latest N" queries

### `signals`
| Column           | Type        | Notes                        |
|------------------|-------------|------------------------------|
| id               | Integer PK  |                              |
| symbol           | String(20)  |                              |
| timeframe        | String(10)  |                              |
| signal_type      | String(20)  | BUY / SELL / NO TRADE        |
| confidence       | Float       | 0–100                        |
| combined_score   | Float       | 0–100                        |
| technical_score  | Float       |                              |
| smc_score        | Float       |                              |
| ml_score         | Float       |                              |
| news_score       | Float       |                              |
| entry            | Float       | Nullable                     |
| stop_loss        | Float       | Nullable                     |
| take_profit      | Float       | Nullable                     |
| created_at       | DateTime    | UTC                          |
| updated_at       | DateTime    | UTC, auto-updated            |

**Index:** `(symbol, timeframe, created_at)` — fast history queries

### `news_articles`
| Column      | Type       | Notes                     |
|-------------|------------|---------------------------|
| id          | Integer PK |                           |
| title       | Text       |                           |
| summary     | Text       | Nullable                  |
| url         | String     |                           |
| source      | String     |                           |
| sentiment   | String(20) | bullish / bearish / neutral |
| published_at| DateTime   |                           |

### `economic_events`
| Column      | Type       | Notes                     |
|-------------|------------|---------------------------|
| id          | Integer PK |                           |
| title       | String     |                           |
| currency    | String(10) |                           |
| impact      | String(10) | low / medium / high       |
| event_time  | DateTime   |                           |
| actual      | String     | Nullable                  |
| forecast    | String     | Nullable                  |
| previous    | String     | Nullable                  |

### `backtest_results`
| Column       | Type       |
|--------------|------------|
| id           | Integer PK |
| symbol       | String     |
| timeframe    | String     |
| start_date   | DateTime   |
| end_date     | DateTime   |
| total_trades | Integer    |
| win_rate     | Float      |
| profit_factor| Float      |
| max_drawdown | Float      |
| created_at   | DateTime   |

### `ml_models`
| Column      | Type       |
|-------------|------------|
| id          | Integer PK |
| symbol      | String     |
| timeframe   | String     |
| model_type  | String     |
| accuracy    | Float      |
| version     | String     |
| trained_at  | DateTime   |

### `system_logs`
| Column     | Type       |
|------------|------------|
| id         | Integer PK |
| level      | String     |
| message    | Text       |
| created_at | DateTime   |

## Migrations

Alembic manages all schema changes. Migration files in `alembic/versions/`:

| Revision               | Description                             |
|------------------------|-----------------------------------------|
| 0001_initial           | Initial schema                          |
| 0002_...               | (as per existing history)               |
| 0003_...               |                                         |
| 0004_signal_enrichment | Signal enrichment fields                |
| 0005_indexes_and_timestamps | Composite indexes + updated_at     |

Run migrations: `alembic upgrade head`
Roll back one step: `alembic downgrade -1`

## Query Patterns

**Latest signals:**
```sql
SELECT * FROM signals
WHERE symbol = 'XAUUSD' AND timeframe = '60'
ORDER BY created_at DESC
LIMIT 50;
-- Uses: ix_signal_symbol_tf_created
```

**Latest candles:**
```sql
SELECT * FROM candles
WHERE symbol = 'XAUUSD' AND timeframe = '60'
ORDER BY timestamp DESC
LIMIT 200;
-- Uses: ix_candle_symbol_tf_ts_desc
```

**Upsert candle (conflict resolution):**
```sql
INSERT INTO candles (...) VALUES (...)
ON CONFLICT ON CONSTRAINT uq_candle_symbol_tf_ts
DO NOTHING;
```
