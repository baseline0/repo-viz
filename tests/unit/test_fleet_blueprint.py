"""The container and manifest agree with the fleet service blueprint."""

from __future__ import annotations

import asyncio
import json

import yaml

from repo_viz.constants import REPO_ROOT
from repo_viz.mcp_server import build_server


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


def test_tool_yaml_matches_registered_tools_and_manifest() -> None:
    declaration = yaml.safe_load((REPO_ROOT / "tool.yaml").read_text(encoding="utf-8"))
    manifest = json.loads((REPO_ROOT / "tool.manifest.json").read_text(encoding="utf-8"))
    registered = {tool.name for tool in asyncio.run(build_server(allow_write=True).list_tools())}

    assert set(declaration["capabilities"]) == registered
    assert declaration["mcp_server"] == manifest["entry_points"]["mcp"]
    assert declaration["boundaries"]["read_only"] is True
    assert declaration["boundaries"]["human_approval_required_for"] == []
    assert (REPO_ROOT / declaration["eval_cases"]).is_file()
