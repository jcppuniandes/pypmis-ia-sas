#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# pypmis database restore
# Usage: bash deploy/vps/restore.sh backups/pypmis_20260511_120000.sql.gz
# ─────────────────────────────────────────────────────────

COMPOSE_FILE="docker-compose.vps.yml"
ENV_FILE=".env"

if [ -z "${1:-}" ]; then
  echo "Usage: bash deploy/vps/restore.sh <backup_file.sql.gz>"
  echo ""
  echo "Available backups:"
  ls -1t backups/pypmis_*.sql.gz 2>/dev/null || echo "  (none found)"
  exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "ERROR: File not found: $BACKUP_FILE"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Run from the repo root."
  exit 1
fi

source "$ENV_FILE"

CHECKSUM_FILE="${BACKUP_FILE}.sha256"
if [ ! -f "$CHECKSUM_FILE" ]; then
  echo "ERROR: Checksum file not found: $CHECKSUM_FILE"
  exit 1
fi
if ! sha256sum -c "$CHECKSUM_FILE"; then
  echo "ERROR: Checksum verification failed for $BACKUP_FILE"
  exit 1
fi
echo "Checksum verified: $CHECKSUM_FILE"

echo "⚠ This will REPLACE the current database with: $BACKUP_FILE"
read -rp "Continue? [y/N] " confirm
if [[ ! "$confirm" =~ ^[yY]$ ]]; then
  echo "Aborted."
  exit 0
fi

echo "Stopping API, worker, and beat..."
docker compose -f "$COMPOSE_FILE" stop api worker beat 2>/dev/null || true

echo "Restoring database..."
gunzip -c "$BACKUP_FILE" | docker compose -f "$COMPOSE_FILE" exec -T db \
  psql -U "${POSTGRES_USER:-pypmis}" -d "${POSTGRES_DB:-pypmis}" --quiet

echo "Running migrations (in case backup is older than current code)..."
docker compose -f "$COMPOSE_FILE" run --rm --no-deps api alembic upgrade head

echo "Restarting services..."
docker compose -f "$COMPOSE_FILE" up -d api worker beat

echo "✓ Restore complete from $BACKUP_FILE"
