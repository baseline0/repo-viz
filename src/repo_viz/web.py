"""Local static server for the viewer, with dev-only audit/work-item POST routes.

The authenticated FastAPI service is in repo_viz.server; this handler is for local viewer development.
"""

from __future__ import annotations

import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from repo_viz.audit import audit_from_artifacts
from repo_viz.constants import REPO_ROOT
from repo_viz.indicators.spec import IndicatorConfig
from repo_viz.workitem import build_work_item_payload, write_work_item

STATIC_DIR = REPO_ROOT / "src" / "repo_viz" / "static"
DATA_DIR = Path(os.environ.get("FLEET_DATA_DIR", str(REPO_ROOT / ".fleet")))


class ViewerHandler(SimpleHTTPRequestHandler):
    """Serve built assets, the selected graph snapshot, and cheap fleet probes."""

    def __init__(
        self,
        *args: Any,
        graph: Path,
        config: IndicatorConfig | None = None,
        indicators: Path | None = None,
        **kwargs: Any,
    ) -> None:
        self.graph = graph
        self.config = config
        self.indicators = indicators
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
        if path == "/config.json":
            body = json.dumps(self.config.to_dict()).encode() if self.config is not None else b"{}"
            self._respond(body, "application/json")
            return
        if path == "/indicators.json":
            body = self.indicators.read_bytes() if self.indicators is not None and self.indicators.is_file() else b"{}"
            self._respond(body, "application/json")
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler contract
        """Dev-only viewer actions; the fleet service exposes authenticated equivalents."""
        path = self.path.split("?", 1)[0]
        if path not in {"/api/audit", "/api/work-item"}:
            self.send_error(404, "unknown action")
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
            node = request.get("node", "")
            if not node:
                raise ValueError("node is required")
            snapshot_arg = request.get("snapshot", "")
            results_arg = request.get("results", "")
            graph_path = Path(snapshot_arg) if snapshot_arg else DATA_DIR / "graph.json"
            results_path = Path(results_arg) if results_arg else DATA_DIR / "indicators.json"
            report = audit_from_artifacts(graph_path, results_path, node)
            if path == "/api/audit":
                payload: dict[str, Any] = report.to_dict()
            else:
                payload = build_work_item_payload(report, snapshot=str(graph_path), results=str(results_path))
                payload["artifacts"] = write_work_item(payload, DATA_DIR / "work-item")
            self._respond(json.dumps(payload).encode(), "application/json")
        except Exception as cause:
            self._respond(
                json.dumps({"error": f"{type(cause).__name__}: {cause}"}).encode(),
                "application/json",
            )

    def _respond(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the terminal readable during pan/zoom debugging."""
        return


def serve(
    graph: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    config: IndicatorConfig | None = None,
    indicators: Path | None = None,
) -> None:
    """Block on a threaded HTTP server serving the viewer and snapshot."""
    handler = partial(
        ViewerHandler,
        graph=graph.resolve(),
        config=config,
        indicators=indicators.resolve() if indicators is not None else None,
    )
    with ThreadingHTTPServer((host, port), handler) as server:
        server.serve_forever()
