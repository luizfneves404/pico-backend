#!/bin/bash

set -e

. /code/.venv/bin/activate

echo "Migrating..."
alembic upgrade head
echo "Migrations complete"

# # Collecting static files. is this needed for fastapi?
# echo "Collecting static files..."
# python manage.py collectstatic --noinput
# echo "Static files collected"
exec python -m app.main
