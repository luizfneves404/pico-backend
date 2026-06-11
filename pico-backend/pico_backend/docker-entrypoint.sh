#!/bin/bash

set -e

# Creating database tables, if they don't exist
echo "Migrating..."
python manage.py migrate --noinput
echo "Migrations complete"

# Collecting static files
echo "Collecting static files..."
python manage.py collectstatic --noinput
echo "Static files collected"
exec daphne -b $DAPHNE_HOST -p 8000 -v 0 --application-close-timeout 300 --http-timeout 300 pico_backend.asgi:application
