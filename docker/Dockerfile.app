FROM python:3.12-bookworm AS builder

ARG INSTALL_TEST=false

ENV POETRY_VIRTUALENVS_IN_PROJECT=1 \
    POETRY_VIRTUALENVS_CREATE=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install poetry

COPY ../pyproject.toml ../poetry.lock ./

# Conditionally install test dependencies if INSTALL_TEST is true
RUN if [ "$INSTALL_TEST" = "true" ]; then \
        poetry install --only=main,app,test --no-interaction --no-root; \
    else \
        poetry install --only=main,app --no-interaction --no-root; \
    fi && rm -rf $POETRY_CACHE_DIR

FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

COPY --from=builder /app/.venv /app/.venv

COPY . /app/

RUN chmod +x /app/docker-entrypoint.sh /app/docker-test-entrypoint.sh