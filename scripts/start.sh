#!/bin/sh
set -eu

echo "Starting Arkhe Identity API..."
echo "Checking database migrations..."
alembic upgrade head
echo "Database migrations are up to date."

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
