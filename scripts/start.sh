#!/bin/sh
set -eu

echo "Starting Arkhe Identity API..."
if ! alembic upgrade head; then
    echo "WARNING: database migrations failed; starting API so health checks and logs remain available."
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --proxy-headers
