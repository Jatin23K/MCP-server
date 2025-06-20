#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
until PGPASSWORD=$DB_PASSWORD psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c '\q' >/dev/null 2>&1; do
  echo "PostgreSQL is not ready yet. Retrying in 5 seconds..."
  sleep 5
done

# Wait for Redis to be ready
echo "Waiting for Redis to be ready..."
until redis-cli -h $REDIS_HOST -p $REDIS_PORT ping >/dev/null 2>&1; do
  echo "Redis is not ready yet. Retrying in 5 seconds..."
  sleep 5
done

# Run database migrations
echo "Running database migrations..."
alembic upgrade head

# Initialize the database if needed
if [ "$INIT_DB" = "true" ]; then
    echo "Initializing the database..."
    python -m app.db.init_db
fi

# Start the application
echo "Starting MCP Server..."
if [ "$FASTAPI_ENV" = "production" ]; then
    # Production: Use gunicorn with uvicorn workers
    exec gunicorn \
        -k uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8000 \
        --workers 4 \
        --worker-connections 1000 \
        --timeout 300 \
        --keep-alive 30 \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        app.main:app
else
    # Development: Use uvicorn with auto-reload
    exec uvicorn \
        --host 0.0.0.0 \
        --port 8000 \
        --reload \
        --reload-dir /app \
        --log-level info \
        app.main:app
fi
