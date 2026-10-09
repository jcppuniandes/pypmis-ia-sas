#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# pypmis database backup
# Creates a timestamped pg_dump in ./backups/
# Usage: bash deploy/vps/backup.sh
# ─────────────────────────────────────────────────────────

COMPOSE_FILE="docker-compose.vps.yml"
ENV_FILE=".env"
BACKUP_DIR="./backups"
BACKUP_KEEP="${BACKUP_KEEP:-14}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Run from the repo root."
  exit 1
fi

source "$ENV_FILE"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="pypmis_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "Backing up database to $BACKUP_DIR/$BACKUP_FILE ..."

docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "${POSTGRES_USER:-pypmis}" -d "${POSTGRES_DB:-pypmis}" \
  --no-owner --no-acl --clean --if-exists \
  | gzip > "$BACKUP_DIR/$BACKUP_FILE"

SIZE=$(du -h "$BACKUP_DIR/$BACKUP_FILE" | cut -f1)
sha256sum "$BACKUP_DIR/$BACKUP_FILE" > "$BACKUP_DIR/$BACKUP_FILE.sha256"
echo "Backup complete: $BACKUP_DIR/$BACKUP_FILE ($SIZE)"
echo "Checksum: $BACKUP_DIR/$BACKUP_FILE.sha256"

# Rotate: keep last BACKUP_KEEP backups
KEEP="$BACKUP_KEEP"
COUNT=$(ls -1 "$BACKUP_DIR"/pypmis_*.sql.gz 2>/dev/null | wc -l)
if [ "$COUNT" -gt "$KEEP" ]; then
  REMOVE=$((COUNT - KEEP))
  echo "Rotating: removing $REMOVE old backup(s)..."
  ls -1t "$BACKUP_DIR"/pypmis_*.sql.gz | tail -n "$REMOVE" | while IFS= read -r old_backup; do
    rm -f "$old_backup" "$old_backup.sha256"
  done
fi
