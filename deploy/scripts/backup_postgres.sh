#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL is required}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/china-succession}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
mkdir -p "$BACKUP_DIR"

timestamp="$(date +%Y%m%d_%H%M%S)"
target="$BACKUP_DIR/china_succession_$timestamp.dump"
tmp_target="$target.tmp"
pg_dump_url="$DATABASE_URL"
pg_dump_url="${pg_dump_url/postgresql+psycopg:\/\//postgresql://}"
pg_dump_url="${pg_dump_url/postgresql+psycopg2:\/\//postgresql://}"

rm -f "$tmp_target"
pg_dump "$pg_dump_url" --format=custom --file="$tmp_target"
mv "$tmp_target" "$target"
find "$BACKUP_DIR" -type f -name 'china_succession_*.dump' -mtime +"$RETENTION_DAYS" -delete

echo "backup created: $target"
