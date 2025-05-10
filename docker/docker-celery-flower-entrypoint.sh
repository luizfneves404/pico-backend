#!/bin/bash

echo "Starting celery flower..."

PYTHONPATH=./pico_django exec celery -A pico_backend flower