# Stage 0: fetch uv (pinned)
ARG UV_VERSION=0.8.22
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# Stage 1: Build
FROM python:3.13-slim AS build

ENV PYTHONUNBUFFERED=True
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV MINIFY=true

# Install build dependencies for Python packages with C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    libffi-dev \
    libssl-dev \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv binaries (from pinned stage)
COPY --from=uv /uv /uvx /bin/

ENV APP_HOME=/app
WORKDIR $APP_HOME

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (cache dependencies in a separate layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev --no-group development --no-group test

# Copy project files
COPY . ./

# Install project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-group development --no-group test

# Stage 2: Runtime
FROM python:3.13-slim

# Install make for database migrations
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    make \
    libmagic1 \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy uv from builder
COPY --from=build /bin/uv /bin/uvx /bin/

# Set the working directory first
ENV APP_HOME=/app
WORKDIR $APP_HOME

# Copy Python environment from builder
COPY --from=build /root/.local/share/uv/python /root/.local/share/uv/python
COPY --from=build /app/.venv /app/.venv

# Set PATH before anything else
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY . ./

# Set GITHUB_SHA at the end to avoid invalidating cache layers
ARG GITHUB_SHA
ENV GITHUB_SHA=$GITHUB_SHA

# Use the entrypoint script
CMD ["/app/docker-entrypoint.sh"]
