"""Typer CLI for repo-viz.

## Specification Map

- ``analyze`` — build and atomically write a graph snapshot for a checkout.
- ``summary`` — print counts from a snapshot without rendering it.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from repo_viz.constants import REPO_ROOT
from repo_viz.indicators.registry import evaluate, write_results
from repo_viz.indicators.spec import EvaluationContext, load_config
from repo_viz.model import GraphSnapshot
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
def evaluate_indicators(
    snapshot_path: Path = typer.Argument(..., help="Snapshot JSON to evaluate"),
    config: Path = typer.Option(REPO_ROOT / "config" / "indicators.toml", "--config"),
    out: Path = typer.Option(Path("indicators.json"), "--out"),
    trigger: str = typer.Option("render", "--trigger", help="render or change"),
    changed: list[Path] = typer.Option([], "--changed", help="Paths touched by a change"),
) -> None:
    """Run configured indicator evaluators over a snapshot."""
    if trigger not in {"render", "change"}:
        raise typer.BadParameter("trigger must be render or change")
    graph = GraphSnapshot.from_dict(json.loads(snapshot_path.read_text(encoding="utf-8")))
    context = EvaluationContext(
        graph=graph,
        trigger=trigger,
        changed_paths=tuple(str(item) for item in changed),
    )
    results = evaluate(load_config(config), context)
    write_results(results, out)
    typer.echo(f"{len(results)} indicator results ({trigger}) -> {out}")


@app.command()
def serve(
    graph: Path = typer.Argument(..., help="Snapshot JSON to display"),
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8080, min=1, max=65535, help="Bind port"),
    config: Path = typer.Option(REPO_ROOT / "config" / "indicators.toml", "--config"),
    indicators: Path | None = typer.Option(None, "--indicators", help="Indicator results JSON"),
) -> None:
    """Serve the built viewer, graph snapshot and indicator configuration."""
    config_object = load_config(config) if config.is_file() else None
    serve_viewer(graph, host=host, port=port, config=config_object, indicators=indicators)


if __name__ == "__main__":
    app()
