"""MCP tool surface: read tools by default, writing tools only with an opt-in."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import typer

from repo_viz import mcp_server
from repo_viz.mcp_server import app as mcp_app
from repo_viz.mcp_server import build_server

READ_TOOLS = {
    "get_summary",
    "get_indicator_results",
    "get_indicator_config",
    "check_indicator_config",
    "audit_component",
}
WRITE_TOOLS = {"analyze", "collect", "prepare_work_item"}
FORBIDDEN = {"approve", "approval", "override", "grant", "bypass", "elevate", "unlock", "authorize"}


def _tools(**flags: bool) -> dict[str, object]:
    tools = asyncio.run(build_server(**flags).list_tools())
    return {tool.name: tool for tool in tools}  # type: ignore[union-attr]


def test_default_tool_list_is_read_only() -> None:
    tools = _tools()
    assert set(tools) == READ_TOOLS
    for tool in tools.values():
        annotations = tool.annotations  # type: ignore[union-attr]
        assert annotations is not None
        assert annotations.read_only_hint is True


def test_opt_in_adds_only_the_writing_tools() -> None:
    tools = _tools(allow_write=True)
    assert set(tools) == READ_TOOLS | WRITE_TOOLS
    for name in WRITE_TOOLS:
        annotations = tools[name].annotations  # type: ignore[union-attr]
        assert annotations is not None
        assert annotations.read_only_hint is False


def test_serve_exposes_allow_write() -> None:
    command = typer.main.get_command(mcp_app)
    options = {opt for param in command.params for opt in param.opts}  # type: ignore[union-attr]
    assert "--allow-write" in options


def test_no_tool_name_or_docstring_contains_a_forbidden_term() -> None:
    tools = _tools(allow_write=True)
    for name, tool in tools.items():
        description = (tool.description or "").lower()  # type: ignore[union-attr]
        assert name.lower() not in FORBIDDEN
        assert all(term not in description for term in FORBIDDEN)


def test_mission_can_supply_its_own_indicator_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom = tmp_path / "mission-indicators.toml"
    monkeypatch.setenv("REPO_VIZ_INDICATOR_CONFIG", str(custom))
    assert mcp_server._config_path() == custom


def test_envelope_returns_config_and_structured_failure(tmp_path: object) -> None:
    server = build_server()
    config = asyncio.run(server.call_tool("get_indicator_config", {}))
    assert config.structured_content["ok"] is True  # type: ignore[index]
    assert config.structured_content["data"]["indicators"]  # type: ignore[index]
    assert config.structured_content["contract"] == "fleet.read-envelope"  # type: ignore[index]
    assert config.structured_content["view"] == "get_indicator_config"  # type: ignore[index]

    failure = asyncio.run(server.call_tool("get_summary", {"snapshot": str(tmp_path / "absent.json")}))
    assert failure.structured_content["ok"] is False  # type: ignore[index]
    assert failure.is_error is True
