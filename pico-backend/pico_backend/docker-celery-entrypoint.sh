#!/bin/bash

echo "Starting celery worker..."

exec celery -A pico_backend worker --pool=prefork --loglevel=info --concurrency=4 -E