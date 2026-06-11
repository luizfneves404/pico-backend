#!/bin/bash

echo "Starting celery flower..."

exec celery -A pico_backend flower