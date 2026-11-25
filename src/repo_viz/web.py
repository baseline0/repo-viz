"""Minimal static server for the built viewer (FastAPI mount comes in Phase 5)."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from repo_viz.constants import REPO_ROOT

STATIC_DIR = REPO_ROOT / "src" / "repo_viz" / "static"


class ViewerHandler(SimpleHTTPRequestHandler):
    """Serve built assets, the selected graph snapshot, and cheap fleet probes."""

    def __init__(self, *args: Any, graph: Path, **kwargs: Any) -> None:
        self.graph = graph
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler contract
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._respond(b"ok", "text/plain")
            return
        if path == "/readyz":
            if self.graph.is_file() and (STATIC_DIR / "index.html").is_file():
                self._respond(b"ready", "text/plain")
            else:
                self.send_error(503, "viewer assets or graph missing")
            return
        if path == "/graph.json":
            self._respond(self.graph.read_bytes(), "application/json")
            return
        super().do_GET()

    def _respond(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the terminal readable during pan/zoom debugging."""
        return


def serve(graph: Path, host: str = "127.0.0.1", port: int = 8080) -> None:
    """Block on a threaded HTTP server serving the viewer and snapshot."""
    handler = partial(ViewerHandler, graph=graph.resolve())
    with ThreadingHTTPServer((host, port), handler) as server:
        server.serve_forever()
