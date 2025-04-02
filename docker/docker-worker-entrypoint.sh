#!/bin/bash

set -e

. /app/.venv/bin/activate

exec arq arq_worker.WorkerSettings
