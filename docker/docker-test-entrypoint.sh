#!/bin/bash

set -e

. /app/.venv/bin/activate

exec pytest
