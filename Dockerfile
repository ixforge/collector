FROM python:3.12-slim AS base

# Mirrors de Debian configurables, por defecto los oficiales. deb.debian.org y
# security.debian.org se degradan cada tanto y hacen fallar el build entero por
# una descarga que no termina. Mismo patron que el Dockerfile del core
ARG DEBIAN_MIRROR=deb.debian.org
ARG DEBIAN_SECURITY_MIRROR=deb.debian.org

RUN sed -i \
      -e "s|URIs: http://deb.debian.org/debian$|URIs: http://${DEBIAN_MIRROR}/debian|" \
      -e "s|URIs: http://deb.debian.org/debian-security$|URIs: http://${DEBIAN_SECURITY_MIRROR}/debian-security|" \
      /etc/apt/sources.list.d/debian.sources \
    && printf 'Acquire::Retries "10";\n' > /etc/apt/apt.conf.d/99-retries \
    && apt-get update && apt-get install -y --no-install-recommends \
    fping \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 1000 ixforge && \
    useradd --uid 1000 --gid ixforge --create-home ixforge

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
# Solo dependencias: el proyecto se instala despues de copiar src y README
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md ./
COPY src/ src/
COPY configs/ configs/
RUN uv sync --frozen --no-dev

RUN chown -R ixforge:ixforge /app
USER ixforge

EXPOSE 9200

ENTRYPOINT ["uv", "run", "ixforge-collector"]
