#!/bin/bash

set -e

. /code/.venv/bin/activate

exec arq app.arq_worker.WorkerSettings
