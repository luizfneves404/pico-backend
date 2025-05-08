#!/bin/bash
set -e

. /code/.venv/bin/activate

echo "Starting celery worker..."

PYTHONPATH=./pico_django exec celery -A pico_backend worker --pool=prefork --loglevel=info --concurrency=4 -E