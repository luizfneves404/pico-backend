#!/bin/bash

set -e

. /code/.venv/bin/activate

exec arq arq_worker.WorkerSettings
