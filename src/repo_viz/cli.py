"""Typer CLI for repo-viz: thin wrappers over testable functions.

## Specification Map

- ``analyze`` — build and atomically write a graph snapshot for a checkout.
- ``summary`` — print counts from a snapshot.
- ``evaluate_indicators`` — run configured evaluators with optional producers.
- ``check_indicators`` — validate config and resolve every evaluator target.
- ``serve`` — block on the built viewer's static server.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from repo_viz.constants import REPO_ROOT
from repo_viz.discovery import list_python_files
from repo_viz.indicators.producers import collect_values
from repo_viz.indicators.registry import evaluate, validate_config, write_results
from repo_viz.indicators.spec import EvaluationContext, load_config
from repo_viz.model import GraphSnapshot
from repo_viz.output import JsonOption, command_output
from repo_viz.snapshot import build_snapshot, snapshot_counts, write_snapshot
from repo_viz.web import serve as serve_viewer

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def analyze(
    repo: Path = typer.Argument(..., help="Repository checkout to analyze"),
    out: Path = typer.Option(Path("graph.json"), "--out", help="Snapshot output path"),
    days: int = typer.Option(30, min=0, help="Window for git churn"),
    json_output: bool = JsonOption,
) -> None:
    """Build a versioned graph snapshot from tracked Python files."""
    with command_output(json_output) as out_stream:
        snapshot = build_snapshot(repo.resolve(), days=days)
        write_snapshot(snapshot, out)
        counts = snapshot_counts(snapshot.to_dict())
        out_stream.echo(
            f"{snapshot.schema}: {counts['nodes']} nodes, {counts['edges']} edges, {counts['ports']} ports -> {out}"
        )
        out_stream.data = {"schema": snapshot.schema, "out": str(out), **counts}


@app.command()
def summary(
    snapshot_path: Path = typer.Argument(..., help="Snapshot JSON to summarize"),
    json_output: bool = JsonOption,
) -> None:
    """Print node/edge/port counts from a snapshot."""
    with command_output(json_output) as out_stream:
        counts = snapshot_counts(json.loads(snapshot_path.read_text(encoding="utf-8")))
        out_stream.echo(f"repo-viz/graph@1: {counts['nodes']} nodes, {counts['edges']} edges, {counts['ports']} ports")
        out_stream.data = counts


@app.command()
def evaluate_indicators(
    snapshot_path: Path = typer.Argument(..., help="Snapshot JSON to evaluate"),
    config: Path = typer.Option(REPO_ROOT / "config" / "indicators.toml", "--config"),
    out: Path = typer.Option(Path("indicators.json"), "--out"),
    trigger: str = typer.Option("render", "--trigger", help="render or change"),
    changed: list[Path] = typer.Option([], "--changed", help="Paths touched by a change"),
    repo: Path | None = typer.Option(None, "--repo", help="Checkout supplying producer values"),
    json_output: bool = JsonOption,
) -> None:
    """Run configured indicator evaluators over a snapshot."""
    if trigger not in {"render", "change"}:
        raise typer.BadParameter("trigger must be render or change")
    with command_output(json_output) as out_stream:
        graph = GraphSnapshot.from_dict(json.loads(snapshot_path.read_text(encoding="utf-8")))
        values = collect_values(repo.resolve(), list_python_files(repo.resolve())) if repo else {}
        context = EvaluationContext(
            graph=graph,
            trigger=trigger,
            changed_paths=tuple(str(item) for item in changed),
            values=values,
        )
        results = evaluate(load_config(config), context)
        write_results(results, out)
        out_stream.echo(f"{len(results)} indicator results ({trigger}) -> {out}")
        out_stream.data = {"results": len(results), "trigger": trigger, "out": str(out)}


@app.command()
def check_indicators(
    config: Path = typer.Option(REPO_ROOT / "config" / "indicators.toml", "--config"),
    json_output: bool = JsonOption,
) -> None:
    """Validate indicator config and resolve every compute target."""
    with command_output(json_output) as out_stream:
        report = validate_config(load_config(config))
        out_stream.echo(
            f"{report['indicators']} indicators, {report['enabled']} enabled, {len(report['problems'])} problems"
        )
        out_stream.data = report
        failed = not report["ok"]
    if failed:
        raise typer.Exit(1)


@app.command()
def serve(
    graph: Path = typer.Argument(..., help="Snapshot JSON to display"),
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8080, min=1, max=65535, help="Bind port"),
    config: Path = typer.Option(REPO_ROOT / "config" / "indicators.toml", "--config"),
    indicators: Path | None = typer.Option(None, "--indicators", help="Indicator results JSON"),
    json_output: bool = JsonOption,
) -> None:
    """Serve the built viewer, graph snapshot and indicator configuration."""
    with command_output(json_output) as out_stream:
        config_object = load_config(config) if config.is_file() else None
        out_stream.echo(f"serving {graph} on {host}:{port}")
        out_stream.data = {"graph": str(graph), "host": host, "port": port}
    serve_viewer(graph, host=host, port=port, config=config_object, indicators=indicators)


if __name__ == "__main__":
    app()
