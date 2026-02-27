FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    fping \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 ixforge && \
    useradd --uid 1000 --gid ixforge --create-home ixforge

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ src/
COPY configs/ configs/

RUN chown -R ixforge:ixforge /app
USER ixforge

EXPOSE 9200

ENTRYPOINT ["uv", "run", "ixforge-collector"]
