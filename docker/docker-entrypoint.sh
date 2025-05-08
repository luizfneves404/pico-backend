#!/bin/bash

set -e

. /code/.venv/bin/activate

# Creating database tables, if they don't exist
echo "Migrating..."
PYTHONPATH=./pico_django python -m pico_django.manage migrate --noinput
echo "Migrations complete"

# Collecting static files
echo "Collecting static files..."
PYTHONPATH=./pico_django python -m pico_django.manage collectstatic --noinput
echo "Static files collected"

exec python -m app.main
