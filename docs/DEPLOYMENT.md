# Gold AI — Deployment Guide

## Prerequisites

- Docker 24+ and Docker Compose v2
- 4 GB RAM minimum (8 GB recommended for ML training)
- Ports 80 and 443 available

## Quick Start

### 1. Clone and configure

```bash
git clone <repo-url> gold_ai
cd gold_ai
cp .env.example .env
```

### 2. Generate secrets

```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# Copy output into .env:
SECRET_KEY=<output>
```

### 3. Edit `.env`

At minimum set:

```env
SECRET_KEY=<64-char hex>
ADMIN_EMAIL=admin@yourdomain.com
ADMIN_PASSWORD=<strong-password>

# Optional but recommended
TWELVEDATA_API_KEY=<your-key>
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
SENTRY_DSN=<your-sentry-dsn>
```

### 4. Start services

```bash
docker compose up -d
```

Services start in order: `db` → `redis` → `backend` (health-checked) → `frontend` → `nginx`.

### 5. Verify

```bash
curl http://localhost/api/v1/health
# {"status": "ok", "service": "gold-ai", "version": "3.0.0"}
```

## Service Ports

| Service  | Internal Port | Exposed (dev) |
|----------|---------------|---------------|
| nginx    | 80            | 80            |
| backend  | 8001          | —             |
| frontend | 3000          | —             |
| postgres | 5432          | 5432          |
| redis    | 6379          | 6379          |

In production, only port 80 (and 443 for TLS) should be exposed externally.

## Database Migrations

Migrations run automatically on container start via Alembic. To run manually:

```bash
docker compose exec backend alembic upgrade head
```

To create a new migration:

```bash
docker compose exec backend alembic revision --autogenerate -m "description"
```

## Scaling

### Backend workers

The backend uses a single Uvicorn process by default. For production, use Gunicorn:

```dockerfile
# In backend/Dockerfile, change CMD to:
CMD ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8001", "--timeout", "120"]
```

### Redis persistence

For production, enable AOF persistence in Redis:

```yaml
# docker-compose.yml redis service
command: redis-server --appendonly yes --appendfsync everysec
```

## Environment Variable Reference

| Variable                | Required | Default                         | Description                    |
|-------------------------|----------|---------------------------------|--------------------------------|
| DATABASE_URL            | ✅        | —                               | PostgreSQL connection string   |
| REDIS_URL               | ✅        | —                               | Redis connection string        |
| SECRET_KEY              | ✅        | —                               | JWT signing secret (64 chars)  |
| ADMIN_EMAIL             | ✅        | —                               | Seed admin email               |
| ADMIN_PASSWORD          | ✅        | —                               | Seed admin password            |
| CORS_ORIGINS            | ✅        | http://localhost:3000           | Comma-separated allowed origins|
| INTERNAL_BASE_URL       | ✅        | http://localhost:8001           | Docker-internal backend URL    |
| TWELVEDATA_API_KEY      | ➖        | (empty)                         | Twelvedata market data key     |
| POLYGON_API_KEY         | ➖        | (empty)                         | Polygon.io fallback key        |
| TELEGRAM_BOT_TOKEN      | ➖        | (empty)                         | Telegram bot token             |
| TELEGRAM_CHAT_ID        | ➖        | (empty)                         | Default Telegram chat ID       |
| SENTRY_DSN              | ➖        | (empty)                         | Sentry error tracking DSN      |
| SIGNAL_BUY_THRESHOLD    | ➖        | 62.0                            | Composite score BUY threshold  |
| SIGNAL_SELL_THRESHOLD   | ➖        | 38.0                            | Composite score SELL threshold |
| SIGNAL_MIN_CONFIDENCE   | ➖        | 65.0                            | Min confidence for Telegram    |
| ML_MODEL_DIR            | ➖        | /app/models                     | Directory to store .pkl models |
| ACCESS_TOKEN_EXPIRE_MINUTES | ➖   | 30                              | JWT access token TTL           |
| REFRESH_TOKEN_EXPIRE_DAYS   | ➖   | 7                               | JWT refresh token TTL          |

## Health Checks

| Endpoint          | Method | Expected Response               |
|-------------------|--------|---------------------------------|
| /api/v1/health    | GET    | `{"status": "ok"}`             |
| /metrics          | GET    | Prometheus metrics text         |

## Logs

```bash
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Last 100 lines
docker compose logs --tail=100 backend
```

## Backup

### Database

```bash
docker compose exec db pg_dump -U goldai goldai | gzip > backup_$(date +%Y%m%d).sql.gz
```

### Restore

```bash
gunzip < backup_20241201.sql.gz | docker compose exec -T db psql -U goldai goldai
```

## Upgrading

```bash
git pull
docker compose build --no-cache
docker compose up -d
docker compose exec backend alembic upgrade head
```
