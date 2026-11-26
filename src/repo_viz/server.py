"""FastAPI service for repo-viz: probes, authenticated generated API routes, static viewer.

## Specification Map

- ``create_app`` — wires auth middleware, probes, generated router and the static mount.
- ``serve_api`` — uvicorn entry point on port 8080.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from repo_viz.api_routes_autogen import router as generated_router
from repo_viz.auth import authorize
from repo_viz.constants import REPO_ROOT
from repo_viz.web import STATIC_DIR

PROBE_PATHS = {"/healthz", "/readyz", "/ready"}
DATA_DIR = Path(os.environ.get("FLEET_DATA_DIR", str(REPO_ROOT / ".fleet")))


def create_app() -> FastAPI:
    """Build the service; probes stay public and /api/* is authenticated."""
    app = FastAPI(title="repo-viz", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def authenticate(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path.startswith("/api/"):
            problem = authorize(request.method, request.url.path, dict(request.headers))
            if problem is not None:
                status, message = problem
                return JSONResponse({"detail": message}, status_code=status)
        return await call_next(request)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz() -> JSONResponse:
        if DATA_DIR.is_dir() and os.access(DATA_DIR, os.W_OK):
            return JSONResponse({"status": "ready"})
        return JSONResponse({"detail": "data directory unavailable"}, status_code=503)

    @app.get("/ready", deprecated=True)
    async def ready() -> JSONResponse:
        response = await readyz()
        response.headers["Deprecation"] = "true"
        response.headers["Link"] = '</readyz>; rel="successor-version"'
        return response

    app.include_router(generated_router)
    if (STATIC_DIR / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="viewer")
    return app


def serve_api(host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run the service with uvicorn."""
    uvicorn.run(create_app(), host=host, port=port)


app = create_app()
