#!/bin/bash

set -e

. /code/.venv/bin/activate

echo "Migrating..."
alembic upgrade head
echo "Migrations complete"

exec python -m app.main
