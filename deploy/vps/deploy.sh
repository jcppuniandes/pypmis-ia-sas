#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# pypmis VPS deploy script
# Run from the repo root on the VPS after git pull.
# Usage: bash deploy/vps/deploy.sh [--seed] [--fresh]
#   --seed   Enable demo data seeding on first boot
#   --fresh  Wipe volumes and start from scratch (DESTRUCTIVE)
# ─────────────────────────────────────────────────────────

COMPOSE_FILE="docker-compose.vps.yml"
ENV_FILE=".env"
SEED=false
FRESH=false

for arg in "$@"; do
  case $arg in
    --seed)  SEED=true ;;
    --fresh) FRESH=true ;;
    *)       echo "Unknown arg: $arg"; exit 1 ;;
  esac
done

echo "═══════════════════════════════════════"
echo "  pypmis VPS deploy"
echo "═══════════════════════════════════════"

# ── 1. Validate .env ──────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found."
  echo "Copy deploy/vps/.env.example to .env and fill in secrets."
  exit 1
fi

source "$ENV_FILE"

REQUIRED_VARS=(
  POSTGRES_PASSWORD REDIS_PASSWORD AUTH_SECRET_KEY
  METRICS_TOKEN CORS_ORIGINS ALLOWED_HOSTS SITE_ADDRESS
)
for var in "${REQUIRED_VARS[@]}"; do
  val="${!var:-}"
  if [ -z "$val" ]; then
    echo "ERROR: $var is not set in $ENV_FILE"
    exit 1
  fi
done

# Check for placeholder values
if [[ "$AUTH_SECRET_KEY" == *"change_this"* ]]; then
  echo "ERROR: AUTH_SECRET_KEY still has a placeholder value. Generate a real secret:"
  echo "  openssl rand -hex 32"
  exit 1
fi
if [[ "$POSTGRES_PASSWORD" == *"change_this"* ]]; then
  echo "ERROR: POSTGRES_PASSWORD still has a placeholder value."
  exit 1
fi

echo "✓ .env validated"

# ── 2. Fresh start (optional) ────────────────────────
if [ "$FRESH" = true ]; then
  echo "⚠ --fresh: tearing down existing stack and volumes..."
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
fi

# ── 3. Build images ──────────────────────────────────
echo "Building images..."
COMMIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
export COMMIT_SHA
docker compose -f "$COMPOSE_FILE" build --pull

# ── 4. Start infra (db + redis) ─────────────────────
echo "Starting database and Redis..."
docker compose -f "$COMPOSE_FILE" up -d db redis
echo "Waiting for PostgreSQL..."
timeout 60 bash -c 'until docker compose -f '"$COMPOSE_FILE"' exec -T db pg_isready -U ${POSTGRES_USER:-pypmis} -d ${POSTGRES_DB:-pypmis} 2>/dev/null; do sleep 2; done'
echo "Waiting for Redis..."
timeout 30 bash -c 'until docker compose -f '"$COMPOSE_FILE"' exec -T redis redis-cli -a "$REDIS_PASSWORD" ping 2>/dev/null | grep -q PONG; do sleep 2; done'
echo "✓ Infrastructure ready"

# ── 5. Run Alembic migrations ────────────────────────
echo "Running database migrations..."
docker compose -f "$COMPOSE_FILE" run --rm --no-deps api alembic upgrade head
echo "✓ Migrations complete"

# ── 6. Optionally seed demo data ─────────────────────
if [ "$SEED" = true ]; then
  echo "Seeding demo data..."
  docker compose -f "$COMPOSE_FILE" run --rm --no-deps \
    -e SEED_DEMO_DATA=true \
    -e AUTO_CREATE_SCHEMA=false \
    api python -c "
from app.database.session import SessionLocal
from app.database.seed import seed_demo
db = SessionLocal()
try:
    seed_demo(db)
    print('✓ Demo data seeded')
finally:
    db.close()
"
fi

# ── 7. Bring up the full stack ───────────────────────
echo "Starting all services..."
docker compose -f "$COMPOSE_FILE" up -d

# ── 8. Health check ──────────────────────────────────
echo "Waiting for API health..."
RETRIES=0
MAX_RETRIES=30
until curl -sf http://127.0.0.1:8000/api/v1/health/ready >/dev/null 2>&1; do
  RETRIES=$((RETRIES + 1))
  if [ "$RETRIES" -ge "$MAX_RETRIES" ]; then
    echo "ERROR: API did not become healthy after ${MAX_RETRIES} attempts"
    docker compose -f "$COMPOSE_FILE" logs --tail=50 api
    exit 1
  fi
  sleep 2
done
echo "✓ API healthy"

# ── 9. Verify TLS (if not localhost) ─────────────────
if [ "$SITE_ADDRESS" != "localhost" ]; then
  echo "Verifying HTTPS at https://$SITE_ADDRESS ..."
  sleep 5
  if curl -sf "https://$SITE_ADDRESS/api/v1/health" >/dev/null 2>&1; then
    echo "✓ HTTPS working"
  else
    echo "⚠ HTTPS not yet available — Caddy may still be obtaining the certificate."
    echo "  Check: docker compose -f $COMPOSE_FILE logs proxy"
  fi
fi

# ── 10. Summary ──────────────────────────────────────
echo ""
echo "═══════════════════════════════════════"
echo "  Deploy complete!"
echo "═══════════════════════════════════════"
echo ""
echo "  Site:     https://$SITE_ADDRESS"
echo "  API:      https://$SITE_ADDRESS/api/v1/health"
echo "  Metrics:  https://$SITE_ADDRESS/api/v1/ops/metrics"
echo "  Commit:   $COMMIT_SHA"
echo ""
echo "  Useful commands:"
echo "    docker compose -f $COMPOSE_FILE logs -f api"
echo "    docker compose -f $COMPOSE_FILE exec api alembic upgrade head"
echo "    bash deploy/vps/backup.sh"
echo ""
