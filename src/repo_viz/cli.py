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
import os
from pathlib import Path
from typing import Any

import typer

from repo_viz.audit import audit_from_artifacts, write_report
from repo_viz.autogen.api_expose import expose
from repo_viz.constants import REPO_ROOT
from repo_viz.discovery import list_python_files
from repo_viz.indicators.producers import collect_values, coverage_from_json
from repo_viz.indicators.registry import evaluate, validate_config, validate_results, write_results
from repo_viz.indicators.spec import EvaluationContext, load_config
from repo_viz.model import GraphSnapshot
from repo_viz.operations import collect_metrics
from repo_viz.output import JsonOption, command_output
from repo_viz.snapshot import build_snapshot, snapshot_counts, write_snapshot
from repo_viz.web import serve as serve_viewer
from repo_viz.workitem import build_work_item_payload, write_work_item

app = typer.Typer(add_completion=False, no_args_is_help=True)
DATA_DIR = Path(os.environ.get("FLEET_DATA_DIR", str(REPO_ROOT / ".fleet")))


def _artifact_path(value: str, name: str) -> Path:
    """Resolve an optional artifact path against the data directory."""
    return Path(value) if value else DATA_DIR / name


@app.command()
def analyze(
    repo: Path = typer.Option(..., "--repo", help="Repository checkout to analyze"),
    out: Path = typer.Option("graph.json", "--out", help="Snapshot output path"),
    days: int = typer.Option(30, min=0, help="Window for git churn"),
    json_output: bool = JsonOption,
) -> None:
    """Build a versioned graph snapshot from tracked Python files."""
    out = Path(out)
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
    snapshot_path: Path = typer.Option(..., "--snapshot", help="Snapshot JSON to summarize"),
    json_output: bool = JsonOption,
) -> None:
    """Print node/edge/port counts from a snapshot."""
    snapshot_path = Path(snapshot_path)
    with command_output(json_output) as out_stream:
        counts = snapshot_counts(json.loads(snapshot_path.read_text(encoding="utf-8")))
        out_stream.echo(f"repo-viz/graph@1: {counts['nodes']} nodes, {counts['edges']} edges, {counts['ports']} ports")
        out_stream.data = counts


@app.command()
def evaluate_indicators(
    snapshot_path: Path = typer.Option(..., "--snapshot", help="Snapshot JSON to evaluate"),
    config: Path = typer.Option("config/indicators.toml", "--config"),
    out: Path = typer.Option("indicators.json", "--out"),
    trigger: str = typer.Option("render", "--trigger", help="render or change"),
    changed: str = typer.Option("", "--changed", help="Comma-separated changed paths"),
    repo: Path | None = typer.Option(None, "--repo", help="Checkout supplying producer values"),
    coverage: str = typer.Option("", "--coverage", help="pytest-cov JSON report"),
    json_output: bool = JsonOption,
) -> None:
    """Run configured indicator evaluators over a snapshot."""
    if trigger not in {"render", "change"}:
        raise typer.BadParameter("trigger must be render or change")
    config = Path(config)
    out = Path(out)
    repo = Path(repo) if repo is not None else None
    with command_output(json_output) as out_stream:
        graph = GraphSnapshot.from_dict(json.loads(snapshot_path.read_text(encoding="utf-8")))
        values = collect_values(repo.resolve(), list_python_files(repo.resolve())) if repo else {}
        context = EvaluationContext(
            graph=graph,
            trigger=trigger,
            changed_paths=tuple(item for item in changed.split(",") if item),
            values=values,
            coverage=coverage_from_json(Path(coverage)) if coverage else {},
        )
        results = evaluate(load_config(config), context)
        write_results(results, out)
        out_stream.echo(f"{len(results)} indicator results ({trigger}) -> {out}")
        out_stream.data = {"results": len(results), "trigger": trigger, "out": str(out)}


@app.command()
def check_indicators(
    config: Path = typer.Option("config/indicators.toml", "--config"),
    json_output: bool = JsonOption,
) -> None:
    """Validate indicator config and resolve every compute target."""
    config = Path(config)
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
def check_results(
    results: str = typer.Option("indicators.json", "--results", help="Indicator results JSON"),
    json_output: bool = JsonOption,
) -> dict[str, Any]:
    """Validate an indicator-results artifact."""
    with command_output(json_output) as out_stream:
        report = validate_results(json.loads(Path(results).read_text(encoding="utf-8")))
        out_stream.echo(f"{report['results']} results, {len(report['problems'])} problems")
        out_stream.data = report
    return report


@app.command()
def serve(
    graph: Path = typer.Option(..., "--graph", help="Snapshot JSON to display"),
    host: str = typer.Option("127.0.0.1", help="Bind address"),
    port: int = typer.Option(8080, min=1, max=65535, help="Bind port"),
    config: Path = typer.Option("config/indicators.toml", "--config"),
    indicators: Path | None = typer.Option(None, "--indicators", help="Indicator results JSON"),
    json_output: bool = JsonOption,
) -> None:
    """Serve the built viewer, graph snapshot and indicator configuration."""
    graph = Path(graph)
    config = Path(config)
    indicators = Path(indicators) if indicators is not None else None
    with command_output(json_output) as out_stream:
        config_object = load_config(config) if config.is_file() else None
        out_stream.echo(f"serving {graph} on {host}:{port}")
        out_stream.data = {"graph": str(graph), "host": host, "port": port}
    serve_viewer(graph, host=host, port=port, config=config_object, indicators=indicators)


@app.command()
@expose(path="/api/v1/collect", method="POST")
def collect(
    repo: Path = typer.Option(..., "--repo", help="Checkout to collect from"),
    out_dir: str = typer.Option("data", "--out-dir", help="Artifact directory"),
    trigger: str = typer.Option("render", "--trigger", help="render or change"),
    days: int = typer.Option(30, "--days", min=0),
    coverage: str = typer.Option("", "--coverage", help="pytest-cov JSON report"),
    config: str = typer.Option("", "--config", help="Indicator config for this target repo"),
    json_output: bool = typer.Option(False, "--json"),
) -> dict[str, Any]:
    """Collect a snapshot, producer values and indicator results for an agent."""
    repo = Path(repo)
    resolved_out_dir = Path(out_dir)
    with command_output(json_output) as out_stream:
        report = collect_metrics(
            repo.resolve(),
            resolved_out_dir,
            Path(config) if config else Path(os.environ.get("REPO_VIZ_INDICATOR_CONFIG", "config/indicators.toml")),
            trigger=trigger,
            days=days,
            coverage_path=coverage,
        )
        out_stream.echo(f"collected {report['results']} results -> {resolved_out_dir}")
        out_stream.data = report
    return report


@app.command()
def api(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8080, "--port", min=1, max=65535),
    json_output: bool = JsonOption,
) -> None:
    """Serve the authenticated FastAPI service."""
    from repo_viz.server import serve_api

    with command_output(json_output) as out_stream:
        out_stream.echo(f"serving API on {host}:{port}")
        out_stream.data = {"host": host, "port": port}
    serve_api(host=host, port=port)


@app.command()
@expose(path="/api/v1/audit", method="POST")
def audit(
    node: str = typer.Option(..., "--node", help="Node id to audit"),
    snapshot: str = typer.Option("", "--snapshot"),
    results: str = typer.Option("", "--results"),
    out: str = typer.Option("", "--out"),
    json_output: bool = JsonOption,
) -> dict[str, Any]:
    """Audit one component from existing artifacts."""
    with command_output(json_output) as out_stream:
        report = audit_from_artifacts(
            _artifact_path(snapshot, "graph.json"),
            _artifact_path(results, "indicators.json"),
            node,
        )
        if out:
            write_report(report, Path(out))
        payload = report.to_dict()
        out_stream.echo(f"{len(report.findings)} findings for {report.node_label}")
        out_stream.data = payload
    return payload


@app.command()
@expose(path="/api/v1/work-item", method="POST")
def prepare_work_item(
    node: str = typer.Option(..., "--node", help="Node id to prepare a request for"),
    snapshot: str = typer.Option("", "--snapshot"),
    results: str = typer.Option("", "--results"),
    out_dir: str = typer.Option("", "--out-dir"),
    json_output: bool = JsonOption,
) -> dict[str, Any]:
    """Prepare a human-authorized work-item request from an audit."""
    with command_output(json_output) as out_stream:
        graph_path = _artifact_path(snapshot, "graph.json")
        results_path = _artifact_path(results, "indicators.json")
        report = audit_from_artifacts(graph_path, results_path, node)
        payload = build_work_item_payload(
            report,
            snapshot=str(graph_path),
            results=str(results_path),
        )
        paths = write_work_item(payload, _artifact_path(out_dir, "work-item")) if out_dir else {}
        payload["artifacts"] = paths
        out_stream.echo(f"prepared {payload['id']} ({payload['status']})")
        out_stream.data = payload
    return payload


@app.command()
def assess(
    repo: Path = typer.Option(..., "--repo", help="Repository checkout to assess"),
    out: str = typer.Option("", "--out", help="Optional output JSON path for the assessment report"),
    days: int = typer.Option(30, "--days", min=0, help="Window for git churn"),
    config: str = typer.Option("", "--config", help="Optional indicator configuration path"),
    json_output: bool = JsonOption,
) -> dict[str, Any]:
    """Assess a repository, computing Lift, Squeeze, and ROI-ranked refactoring candidates."""
    from repo_viz.assessment import assess_repo, write_assessment

    with command_output(json_output) as out_stream:
        assessment = assess_repo(
            repo,
            days=days,
            config_path=Path(config) if config else None,
        )
        payload = assessment.to_dict()
        if out:
            write_assessment(payload, Path(out))
        out_stream.echo(
            f"Assessed {assessment.repo_name}: {assessment.degraded_nodes}/{assessment.total_nodes} degraded nodes, "
            f"{len(assessment.candidates)} refactoring candidates, avg ROI {assessment.average_roi}"
        )
        out_stream.data = payload
    return payload


@app.command()
def assess_fleet(
    root: Path = typer.Option(..., "--root", help="Root directory containing fleet-* and tool-* repositories"),
    patterns: str = typer.Option("fleet-*,tool-*", "--patterns", help="Comma-separated glob patterns to match"),
    out: str = typer.Option("", "--out", help="Optional output JSON path for the fleet assessment"),
    days: int = typer.Option(30, "--days", min=0, help="Window for git churn"),
    config: str = typer.Option("", "--config", help="Optional indicator configuration path"),
    json_output: bool = JsonOption,
) -> dict[str, Any]:
    """Walk all fleet and tool repositories, compiling a unified antipattern and refactoring ledger."""
    from repo_viz.assessment import walk_fleet, write_assessment

    pattern_list = tuple(p.strip() for p in patterns.split(",") if p.strip())
    with command_output(json_output) as out_stream:
        fleet_assessment = walk_fleet(
            root,
            patterns=pattern_list,
            days=days,
            config_path=Path(config) if config else None,
        )
        payload = fleet_assessment.to_dict()
        if out:
            write_assessment(payload, Path(out))
        out_stream.echo(
            f"Fleet assessment complete: {fleet_assessment.total_repos} repos, "
            f"{fleet_assessment.total_candidates} total refactoring candidates identified"
        )
        out_stream.data = payload
    return payload


if __name__ == "__main__":
    app()
