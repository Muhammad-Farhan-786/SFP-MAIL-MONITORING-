#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
restore_path="${1:?Usage: scripts/restore.sh path/to/backup.dump --confirm-replace}"
[[ "${2:-}" == '--confirm-replace' ]] || { echo 'Restore replaces database contents. Pass --confirm-replace after backing up.'; exit 2; }
[[ -f "$restore_path" && -f "$restore_path.sha256" ]] || { echo 'Backup and checksum are required.'; exit 2; }
sha256sum -c "$restore_path.sha256"
docker compose up -d --wait db redis
docker compose stop backend worker scheduler
docker compose exec -T db pg_restore -U emailhealth -d emailhealth --clean --if-exists --no-owner --exit-on-error < "$restore_path"
docker compose run --rm migrate
docker compose up -d backend worker scheduler
