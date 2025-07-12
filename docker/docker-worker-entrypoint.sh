#!/bin/bash

set -e

. /code/.venv/bin/activate

exec python -m app.arq_worker
