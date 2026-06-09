# Gold AI — Security Report

## Summary

Security audit and hardening performed as Phase 4 of the refactor. All critical findings were remediated.

## Critical Findings (Resolved)

### 1. Hardcoded Credentials in docker-compose.yml ✅ Fixed

**Before:**
```yaml
environment:
  POSTGRES_PASSWORD: goldai123
  SECRET_KEY: supersecretkey123
```

**After:** All secrets use `${VAR:?error}` — Docker Compose aborts if variable is unset.

### 2. Predictable JWT Secret ✅ Fixed

The default `SECRET_KEY` was a short, dictionary-guessable string. It is now:
- A 64-character random hex value (generated at deploy time)
- Documented in `.env.example` with generation instructions
- Required env var — startup fails without it

### 3. No Token Revocation on Logout ✅ Fixed

**Before:** Logout had no effect — stolen tokens remained valid until expiry.

**After:** Redis-backed JWT blacklist:
- Every token includes a `jti` (UUID) claim
- `POST /api/v1/auth/logout` blacklists the `jti` in Redis with TTL = token expiry
- `POST /api/v1/auth/refresh` blacklists the old refresh token (rotation)
- `decode_token()` checks blacklist before accepting any token
- Degrades gracefully when Redis is unavailable (tokens remain valid — fail-open)

### 4. Telegram Bot Called localhost in Docker ✅ Fixed

**Before:** `http://localhost:8001` — resolves to the Telegram container itself, not the backend.

**After:** `_INTERNAL_URL = os.environ.get("INTERNAL_BASE_URL", "http://localhost:8001")`. In Docker Compose, `INTERNAL_BASE_URL=http://backend:8001`.

### 5. CORS Wildcard ✅ Fixed

**Before:** `allow_methods=["*"]` with no origin restrictions.

**After:** Explicit methods (`GET POST PUT DELETE OPTIONS`), explicit headers (`Authorization Content-Type X-Requested-With`), origins from `CORS_ORIGINS` env var.

## Rate Limiting

`slowapi` limits all endpoints to **200 requests/minute per IP** by default. Sensitive endpoints can override:

```python
@limiter.limit("5/minute")
async def login(request: Request, ...):
```

## Observability

Errors are tracked via Sentry (when `SENTRY_DSN` is set). All SQL queries and FastAPI requests are traced at 10% sample rate.

## Remaining Recommendations

| Priority | Finding                                     | Status   |
|----------|---------------------------------------------|----------|
| High     | Add TLS/HTTPS via Let's Encrypt or cert     | Pending  |
| High     | Rotate `SECRET_KEY` procedure documented    | Pending  |
| Medium   | Brute-force protection on `/auth/login`     | Partial (rate limit) |
| Medium   | Email verification on registration          | Not implemented |
| Low      | Audit log for admin actions                 | Not implemented |
| Low      | HSTS header in Nginx                        | Pending  |

## OWASP Top 10 Coverage

| #   | Risk                           | Status       |
|-----|--------------------------------|--------------|
| A01 | Broken Access Control          | ✅ JWT + admin check |
| A02 | Cryptographic Failures         | ✅ PBKDF2-SHA256 passwords |
| A03 | Injection                      | ✅ SQLAlchemy ORM (parameterized) |
| A04 | Insecure Design                | ⚠️ No email verification |
| A05 | Security Misconfiguration      | ✅ No defaults in prod |
| A06 | Vulnerable Components          | ⚠️ No automated dependency scan |
| A07 | Auth and Session Management    | ✅ JWT rotation + blacklist |
| A08 | Software Integrity Failures    | ✅ Pinned requirements |
| A09 | Logging and Monitoring         | ✅ Sentry + Prometheus |
| A10 | SSRF                           | ⚠️ Webhook/external URLs not validated |
