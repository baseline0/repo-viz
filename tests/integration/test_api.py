"""Authenticated API surface using FastAPI's in-process test client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repo_viz import server


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(server, "DATA_DIR", tmp_path)
    monkeypatch.setenv("FLEET_API_KEY", "master-key")
    return TestClient(server.create_app())


def test_probes_are_public(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200
    ready = client.get("/ready")
    assert ready.status_code == 200
    assert ready.headers["Deprecation"] == "true"


def test_mcp_requires_a_key(client: TestClient) -> None:
    assert client.post("/mcp", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1}).status_code == 401


def test_collect_requires_a_key(client: TestClient, tmp_repo: Path, tmp_path: Path) -> None:
    response = client.post(
        "/api/v1/collect",
        json={"repo": str(tmp_repo), "out_dir": str(tmp_path / "data")},
    )
    assert response.status_code == 401


def test_collect_runs_with_master_key(client: TestClient, tmp_repo: Path, tmp_path: Path) -> None:
    out_dir = tmp_path / "artifacts"
    response = client.post(
        "/api/v1/collect",
        json={"repo": str(tmp_repo), "out_dir": str(out_dir)},
        headers={"Authorization": "Bearer master-key"},
    )
    assert response.status_code == 200, response.text
    payload = json.loads(response.text)
    assert Path(payload["graph"]).is_file()
    assert Path(payload["indicators"]).is_file()
    assert payload["results"] > 0


def test_read_only_key_cannot_post(
    client: TestClient, tmp_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "FLEET_API_KEYS",
        json.dumps({"reader-key": {"identity": "reader", "allowed_tools": ["repo-viz"], "read_only": True}}),
    )
    response = client.post(
        "/api/v1/collect",
        json={"repo": str(tmp_repo), "out_dir": str(tmp_path / "data")},
        headers={"Authorization": "Bearer reader-key"},
    )
    assert response.status_code == 403
