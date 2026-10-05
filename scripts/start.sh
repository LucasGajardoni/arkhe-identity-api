#!/bin/sh
set -eu

echo "Starting Arkhe Identity API..."
echo "Checking database migrations..."

tentativa=1

while ! alembic upgrade head; do
    if [ "$tentativa" -ge 10 ]; then
        echo "Database migrations failed after 10 attempts."
        exit 1
    fi

    echo "Database unavailable. Retrying migration in 3 seconds... ($tentativa/10)"
    tentativa=$((tentativa + 1))
    sleep 3
done

echo "Database migrations are up to date."

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
