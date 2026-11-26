"""MCP surface for repo-viz: read tools by default, file-writing tools behind an opt-in.

## Specification Map

- ``build_server`` — MCPServer with read tools always and write tools only with ``allow_write``.
- ``app`` — stdio Typer entry point (`repo-viz-mcp`).
"""

from __future__ import annotations

import functools
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from repo_viz.audit import audit_from_artifacts
from repo_viz.constants import REPO_ROOT
from repo_viz.indicators.registry import validate_config
from repo_viz.indicators.spec import load_config
from repo_viz.operations import collect_metrics
from repo_viz.snapshot import build_snapshot, snapshot_counts, write_snapshot
from repo_viz.workitem import build_work_item_payload, write_work_item

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
WRITES_FILES = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
DATA_DIR = Path(os.environ.get("FLEET_DATA_DIR", str(REPO_ROOT / ".fleet")))
CONFIG_PATH = REPO_ROOT / "config" / "indicators.toml"


def _config_path() -> Path:
    """A mission may supply thresholds tuned for its own target repository."""
    return Path(os.environ.get("REPO_VIZ_INDICATOR_CONFIG", str(CONFIG_PATH)))


def _envelope(view: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Return one fleet read-envelope with success data or a structured failure."""

    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> CallToolResult:
            try:
                payload: dict[str, Any] = {
                    "ok": True,
                    "contract": "fleet.read-envelope",
                    "version": "1.0",
                    "source": "repo-viz",
                    "view": view,
                    "data": function(*args, **kwargs),
                }
            except Exception as cause:
                payload = {
                    "ok": False,
                    "contract": "fleet.read-envelope",
                    "version": "1.0",
                    "source": "repo-viz",
                    "view": view,
                    "error": {"code": "EXECUTION_FAILED", "message": f"{type(cause).__name__}: {cause}"},
                }
            text = json.dumps(payload, indent=2, sort_keys=True)
            return CallToolResult(
                content=[TextContent(type="text", text=text)],
                is_error=payload["ok"] is not True,
                structured_content=payload,
            )

        return wrapped  # type: ignore[return-value]

    return decorate


def _artifact_path(value: str, default: Path) -> Path:
    return Path(value) if value else default


def build_server(*, allow_write: bool = False) -> MCPServer:
    """Build the server with read tools and, on opt-in, the file-writing tools."""
    server = MCPServer("repo-viz", instructions="Repository structure and metric collection.")

    @server.tool(name="get_summary", annotations=READ_ONLY)
    @_envelope("get_summary")
    def get_summary(snapshot: str = "") -> dict[str, Any]:
        """Return node, edge and port counts from a snapshot artifact."""
        path = _artifact_path(snapshot, DATA_DIR / "graph.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        return snapshot_counts(payload)

    @server.tool(name="get_indicator_results", annotations=READ_ONLY)
    @_envelope("get_indicator_results")
    def get_indicator_results(node_id: str = "", results: str = "") -> dict[str, Any]:
        """Return indicator results, optionally filtered to one node."""
        path = _artifact_path(results, DATA_DIR / "indicators.json")
        rows = json.loads(path.read_text(encoding="utf-8"))["results"]
        if node_id:
            rows = [row for row in rows if row["node_id"] == node_id]
        return {"results": rows}

    @server.tool(name="get_indicator_config", annotations=READ_ONLY)
    @_envelope("get_indicator_config")
    def get_indicator_config() -> dict[str, Any]:
        """Return slot positions, palettes, thresholds and evidence references."""
        return load_config(_config_path()).to_dict()

    @server.tool(name="check_indicator_config", annotations=READ_ONLY)
    @_envelope("check_indicator_config")
    def check_indicator_config() -> dict[str, Any]:
        """Resolve every configured evaluator and report problems."""
        return validate_config(load_config(_config_path()))

    @server.tool(name="audit_component", annotations=READ_ONLY)
    @_envelope("audit_component")
    def audit_component(node_id: str, snapshot: str = "", results: str = "") -> dict[str, Any]:
        """Return an audit report for one component from existing artifacts."""
        report = audit_from_artifacts(
            _artifact_path(snapshot, DATA_DIR / "graph.json"),
            _artifact_path(results, DATA_DIR / "indicators.json"),
            node_id,
        )
        return report.to_dict()

    if allow_write:

        @server.tool(name="analyze", annotations=WRITES_FILES)
        @_envelope("analyze")
        def analyze(repo: str, out: str = "") -> dict[str, Any]:
            """Write a versioned graph snapshot for a checkout."""
            path = _artifact_path(out, DATA_DIR / "graph.json")
            path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = build_snapshot(Path(repo), days=30)
            write_snapshot(snapshot, path)
            return {"schema": snapshot.schema, "out": str(path), **snapshot_counts(snapshot.to_dict())}

        @server.tool(name="collect", annotations=WRITES_FILES)
        @_envelope("collect")
        def collect(
            repo: str,
            out_dir: str = "",
            trigger: str = "render",
            coverage: str = "",
        ) -> dict[str, Any]:
            """Write a snapshot and indicator results for a checkout."""
            return collect_metrics(
                Path(repo),
                _artifact_path(out_dir, DATA_DIR),
                _config_path(),
                trigger=trigger,
                days=30,
                coverage_path=coverage,
            )

        @server.tool(name="prepare_work_item", annotations=WRITES_FILES)
        @_envelope("prepare_work_item")
        def prepare_work_item(
            node_id: str,
            snapshot: str = "",
            results: str = "",
            out_dir: str = "",
        ) -> dict[str, Any]:
            """Write a work-item request artifact for one audited component."""
            graph_path = _artifact_path(snapshot, DATA_DIR / "graph.json")
            results_path = _artifact_path(results, DATA_DIR / "indicators.json")
            report = audit_from_artifacts(graph_path, results_path, node_id)
            payload = build_work_item_payload(
                report,
                snapshot=str(graph_path),
                results=str(results_path),
            )
            payload["artifacts"] = write_work_item(payload, _artifact_path(out_dir, DATA_DIR / "work-item"))
            return payload

    return server


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def serve(allow_write: bool = typer.Option(False, "--allow-write")) -> None:
    """Run the MCP server over stdio."""
    build_server(allow_write=allow_write).run("stdio")


if __name__ == "__main__":
    app()
