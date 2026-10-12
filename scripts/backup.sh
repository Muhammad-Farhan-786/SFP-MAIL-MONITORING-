#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
backup_path="backups/emailhealth-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T db pg_dump -U emailhealth -d emailhealth -Fc > "$backup_path.tmp"
mv "$backup_path.tmp" "$backup_path"
sha256sum "$backup_path" > "$backup_path.sha256"
echo "Database backup created: $backup_path"
