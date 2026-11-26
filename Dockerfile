# syntax=docker/dockerfile:1
# repo-viz service image: Svelte/Canvas2D viewer built from frontend/, Python FastAPI+MCP service at port 8080.
# Built by infrastructure/scripts/k8s/build-tool-image.sh; do not run a bare docker build from this repo.

FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runtime
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    FLEET_DATA_DIR=/data
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY config ./config
COPY schemas ./schemas
COPY --from=frontend /app/src/repo_viz/static ./src/repo_viz/static
RUN uv sync --frozen --no-dev --no-install-project \
    && uv pip install --no-deps . \
    && useradd --uid 10001 --user-group --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && mkdir -p /data && chown -R app:app /data /app

VOLUME ["/data"]
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"
CMD ["sh", "-c", "exec /app/.venv/bin/python -m repo_viz.cli api --host 0.0.0.0 --port 8080"]
