FROM python:3.12-bookworm AS builder

ARG INSTALL_TEST=false

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PYTHONUNBUFFERED=1

WORKDIR /code

RUN pip install poetry

COPY pyproject.toml poetry.lock ./

# Conditionally install test dependencies if INSTALL_TEST is true
RUN if [ "$INSTALL_TEST" = "true" ]; then \
        poetry install --only=main,test --no-interaction --no-root; \
    else \
        poetry install --only=main --no-interaction --no-root; \
    fi && rm -rf $POETRY_CACHE_DIR

FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update && apt-get install --no-install-recommends -y postgresql-client libmagic1 tesseract-ocr && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /code

ENV PATH="/code/.venv/bin:$PATH"

COPY --from=builder /code/.venv /code/.venv

COPY . /code/

RUN chmod +x /code/docker/docker-entrypoint.sh /code/docker/docker-test-entrypoint.sh /code/docker/docker-worker-entrypoint.sh