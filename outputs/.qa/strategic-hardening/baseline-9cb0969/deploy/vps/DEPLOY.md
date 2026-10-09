# Deployment Runbook — pypmis VPS

## Prerequisites

| Requirement | Minimum |
|---|---|
| VPS | Ubuntu 22.04+ / Debian 12+ |
| RAM | 2 GB (4 GB recommended) |
| Disk | 20 GB SSD |
| Docker | 24.x + Compose v2 |
| Domain | A record pointing to VPS IP |
| Ports | 80, 443 open inbound |

## First-time setup

### 1. Install Docker on VPS

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in
```

### 2. Clone and configure

```bash
git clone <repo-url> pypmis && cd pypmis

# Create .env from template
cp deploy/vps/.env.example .env
```

### 3. Generate secrets

```bash
# Generate AUTH_SECRET_KEY (64 hex chars)
openssl rand -hex 32

# Generate POSTGRES_PASSWORD
openssl rand -base64 24

# Generate REDIS_PASSWORD
openssl rand -base64 24

# Generate METRICS_TOKEN
openssl rand -hex 16
```

Edit `.env` with the generated values:

```
POSTGRES_PASSWORD=<generated>
REDIS_PASSWORD=<generated>
AUTH_SECRET_KEY=<generated>
METRICS_TOKEN=<generated>
CORS_ORIGINS=https://yourdomain.com
ALLOWED_HOSTS=yourdomain.com
SITE_ADDRESS=yourdomain.com
```

### 4. Deploy

```bash
# First deploy with demo data
bash deploy/vps/deploy.sh --seed

# First deploy without demo data (empty DB)
bash deploy/vps/deploy.sh
```

The script will:
1. Validate `.env` (no placeholder secrets)
2. Build Docker images
3. Start PostgreSQL + Redis
4. Run Alembic migrations
5. Optionally seed demo data
6. Start all services (API, worker, beat, frontend, Caddy proxy)
7. Wait for API health check
8. Verify HTTPS if not localhost

### 5. Verify

```bash
# Health check
curl https://yourdomain.com/api/v1/health/ready

# Logs
docker compose -f docker-compose.vps.yml logs -f api
```

## Routine operations

### Update to latest code

```bash
git pull origin main
bash deploy/vps/deploy.sh
```

The deploy script is idempotent — it rebuilds, migrates, and restarts.

### Database backup

```bash
# Manual backup
bash deploy/vps/backup.sh

# Automated daily backup (add to crontab)
crontab -e
# Add: 0 3 * * * cd /path/to/pypmis && bash deploy/vps/backup.sh >> backups/cron.log 2>&1
```

Backups are stored in `./backups/` and auto-rotated (keeps last 14).

### Database restore

```bash
bash deploy/vps/restore.sh backups/pypmis_20260511_120000.sql.gz
```

### View logs

```bash
# All services
docker compose -f docker-compose.vps.yml logs -f

# Specific service
docker compose -f docker-compose.vps.yml logs -f api
docker compose -f docker-compose.vps.yml logs -f worker
docker compose -f docker-compose.vps.yml logs -f proxy
```

### Restart a service

```bash
docker compose -f docker-compose.vps.yml restart api
docker compose -f docker-compose.vps.yml restart worker beat
```

### Scale API workers

The API runs 4 gunicorn workers by default. To adjust:

```bash
# Temporarily override
docker compose -f docker-compose.vps.yml exec api \
  gunicorn app.main:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Run migrations manually

```bash
docker compose -f docker-compose.vps.yml exec api alembic upgrade head
```

### Create a user via CLI

```bash
docker compose -f docker-compose.vps.yml exec api python -c "
from app.database.session import SessionLocal
from app.domain.models import UserAccount, AuthCredential
from app.core.security import hash_password
from sqlalchemy import select

db = SessionLocal()
tenant_id = 1  # demo-energy tenant
user = UserAccount(tenant_id=tenant_id, email='you@example.com', full_name='Your Name', title='Admin', status='active')
db.add(user)
db.flush()
db.add(AuthCredential(tenant_id=tenant_id, user_id=user.id, provider='local', password_hash=hash_password('your-password'), is_active=True))
db.commit()
print(f'Created user id={user.id}')
db.close()
"
```

## Architecture

```
Internet
  │
  ▼  :80/:443
┌──────────────┐
│  Caddy proxy │  ← automatic TLS via Let's Encrypt
└──────┬───────┘
       │
  ┌────┴─────┐
  ▼          ▼
┌──────┐  ┌──────────┐
│ nginx│  │ gunicorn  │  ← 4 UvicornWorkers
│(SPA) │  │ (FastAPI) │
└──────┘  └────┬─────┘
               │
         ┌─────┼─────┐
         ▼     ▼     ▼
      ┌────┐ ┌─────┐ ┌──────┐
      │ PG │ │Redis│ │Worker│ + Beat
      └────┘ └─────┘ └──────┘
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `502 Bad Gateway` | API not ready yet | Wait 30s, check `docker compose logs api` |
| `HTTPS not working` | Caddy still obtaining cert | Check `docker compose logs proxy`, ensure port 80/443 open |
| `Migrations fail` | DB not ready | Ensure `docker compose logs db` shows "ready to accept connections" |
| `CORS errors in browser` | Wrong `CORS_ORIGINS` | Set to `https://yourdomain.com` (exact match) |
| `Rate limited (429)` | Too many requests | Adjust `RATE_LIMIT_REQUESTS` in .env |
| `500 errors` | Check API logs | `docker compose logs api --tail=100` |
| `Worker not processing` | Check worker logs | `docker compose logs worker`, verify Redis connection |
