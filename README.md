# GOLD AI - Trading Intelligence (Phase 1)

Run Phase 1 locally (development):

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Configure environment in `.env` (optional). By default uses sqlite `./dev.db`.

3. Initialize database:

```bash
python src/scripts/init_db.py
```

4. Run the FastAPI app:

```bash
uvicorn src.main:app --reload --port 8000
```

API root: http://localhost:8000/docs

Phase 1 includes: system scaffold, DB models, JWT auth endpoints, OAuth2 token flow, MT5 connector integration, scheduled market data ingestion, EMA/RSI/MACD indicator engine, and market-data API endpoints.

Manual trigger endpoints are also available for development:
- POST /api/v1/market-data/ingest
- GET /api/v1/market-data/scheduler
- POST /api/v1/indicators/recalculate

Migrations (Alembic):

1. Install dependencies (if not already):

```bash
pip install alembic
```

2. Set `DATABASE_URL` in your environment or in `.env`.

3. Create initial migration and apply:

```bash
alembic revision --autogenerate -m "initial"
alembic upgrade head
```

Note: `alembic.ini` defaults to a local sqlite dev DB. Override with `DATABASE_URL` for Postgres.
