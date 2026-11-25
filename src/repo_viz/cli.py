"""Typer CLI for repo-viz.

## Specification Map

- ``analyze`` — build and atomically write a graph snapshot for a checkout.
- ``summary`` — print counts from a snapshot without rendering it.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from repo_viz.snapshot import build_snapshot, write_snapshot
from repo_viz.web import serve as serve_viewer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def analyze(
    repo: Path = typer.Argument(..., help="Repository checkout to analyze"),
    out: Path = typer.Option(Path("graph.json"), "--out", help="Snapshot output path"),
    days: int = typer.Option(30, min=0, help="Window for git churn"),
) -> None:
    """Build a versioned graph snapshot from tracked Python files."""
    snapshot = build_snapshot(repo.resolve(), days=days)
    write_snapshot(snapshot, out)
    typer.echo(
        f"{snapshot.schema}: {len(snapshot.nodes)} nodes, "
        f"{len(snapshot.edges)} macro edges, {len(snapshot.ports)} ports -> {out}"
    )


@app.command()
def summary(snapshot_path: Path = typer.Argument(..., help="Snapshot JSON to summarize")) -> None:
    """Print node/edge/port counts and schema from a snapshot."""
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    typer.echo(
        f"{payload['schema']}: {len(payload['nodes'])} nodes, "
        f"{len(payload['edges'])} macro edges, {len(payload['ports'])} ports"
    )


@app.command()
def serve(
    graph: Path = typer.Argument(..., help="Snapshot JSON to display"),
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8080, min=1, max=65535, help="Bind port"),
) -> None:
    """Serve the built viewer and a graph snapshot over HTTP."""
    serve_viewer(graph, host=host, port=port)


if __name__ == "__main__":
    app()
