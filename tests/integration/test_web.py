"""HTTP surface checks against a local, thread-backed static server.

No external network, GPU, or sibling repo is used.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from collections.abc import Iterator
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from repo_viz import web
from repo_viz.constants import REPO_ROOT
from repo_viz.indicators.spec import load_config


@pytest.fixture
def viewer_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Start a local viewer server backed by temporary artifacts."""
    (tmp_path / "index.html").write_text("viewer", encoding="utf-8")
    monkeypatch.setattr(web, "STATIC_DIR", tmp_path)
    graph = tmp_path / "graph.json"
    graph.write_text('{"schema": "repo-viz/graph@1"}', encoding="utf-8")
    results = tmp_path / "indicators.json"
    results.write_text('{"version": 1, "results": []}', encoding="utf-8")
    handler = partial(
        web.ViewerHandler,
        graph=graph,
        config=load_config(REPO_ROOT / "config" / "indicators.toml"),
        indicators=results,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_probes_and_artifacts(viewer_url: str) -> None:
    """Probes and artifact routes answer without external services."""
    for path in ("/healthz", "/readyz", "/graph.json", "/config.json", "/indicators.json", "/"):
        with urllib.request.urlopen(viewer_url + path, timeout=2) as response:
            assert response.status == 200

    with urllib.request.urlopen(viewer_url + "/graph.json", timeout=2) as response:
        assert json.loads(response.read())["schema"] == "repo-viz/graph@1"
    with urllib.request.urlopen(viewer_url + "/config.json", timeout=2) as response:
        assert len(json.loads(response.read())["indicators"]) == 14
