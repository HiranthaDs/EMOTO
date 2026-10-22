#!/bin/sh
set -eu
mkdir -p "${DATA_DIR:-/var/data}/uploads" "${DATA_DIR:-/var/data}/backups"
cd /app/backend
python -m app.migrate
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" --workers 1 --proxy-headers --forwarded-allow-ips='*'

