FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder
ARG INSTALL_TEST=false

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Configure the Python directory so it is consistent
ENV UV_PYTHON_INSTALL_DIR=/python

# Only use the managed Python version
ENV UV_PYTHON_PREFERENCE=only-managed

ENV PYTHONUNBUFFERED=1

# Install Python before the project for caching
RUN uv python install 3.12

WORKDIR /code
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    if [ "$INSTALL_TEST" = "false" ]; then \
    uv sync --locked --no-install-project --no-dev --no-group test; \
    else \
    uv sync --locked --no-install-project --no-dev; \
    fi
COPY . /code
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ "$INSTALL_TEST" = "false" ]; then \
    uv sync --locked --no-dev --no-group test; \
    else \
    uv sync --locked --no-dev; \
    fi

# Then, use a final image without uv
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

# Copy the Python version
COPY --from=builder --chown=python:python /python /python

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app

# Copy the application from the builder
COPY --from=builder --chown=app:app /code /code

RUN mkdir /code/storage && chown app:app /code/storage

WORKDIR /code

# Place executables in the environment at the front of the path
ENV PATH="/code/.venv/bin:$PATH"

RUN chmod +x /code/docker/docker-entrypoint.sh /code/docker/docker-test-entrypoint.sh /code/docker/docker-worker-entrypoint.sh

USER app