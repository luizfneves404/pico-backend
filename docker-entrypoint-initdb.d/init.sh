#!/bin/bash
set -e

# echo "postgres user role: $POSTGRES_USER"
# echo "Creating database role: $DB_USER"
echo "Creating database: $DB_NAME"

# psql -U $POSTGRES_USER -c "CREATE ROLE $DB_USER WITH LOGIN PASSWORD '$DB_PASSWORD' CREATEDB;"
psql -U $POSTGRES_USER -d postgres -c "CREATE DATABASE $DB_NAME;"