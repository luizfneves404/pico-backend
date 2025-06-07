#!/bin/bash
set -e

. /code/.venv/bin/activate

echo "Starting celery worker and ARQ worker..."

# Start ARQ worker in the background
python -m app.arq_worker &
ARQ_PID=$!

# Start Celery worker
PYTHONPATH=./pico_django exec celery -A pico_backend worker --pool=prefork --loglevel=info --concurrency=4 -E

# If celery exits, kill the ARQ worker too
kill $ARQ_PID