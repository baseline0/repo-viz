"""The container and manifest agree with the fleet service blueprint."""

from __future__ import annotations

import json

from repo_viz.constants import REPO_ROOT


def test_dockerfile_uses_blueprint_port_user_and_data_volume() -> None:
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:10001" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert "FLEET_DATA_DIR=/data" in dockerfile
    assert 'VOLUME ["/data"]' in dockerfile
    assert "--host 0.0.0.0 --port 8080" in dockerfile


def test_manifest_pins_probes_and_mcp_endpoint() -> None:
    manifest = json.loads((REPO_ROOT / "tool.manifest.json").read_text(encoding="utf-8"))
    assert manifest["probes"] == {"liveness": "/healthz", "readiness": "/readyz"}
    assert manifest["mcp"]["endpoint"] == "/mcp"
    assert manifest["mcp"]["port"] == 8080
    assert manifest["mcp"]["read_only_by_default"] is True
