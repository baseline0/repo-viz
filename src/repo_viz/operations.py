"""Orchestration shared by the CLI and the generated API routes.

## Specification Map

- ``collect_metrics`` — build a snapshot, run producers, evaluate indicators, write artifacts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repo_viz.discovery import list_python_files
from repo_viz.indicators.producers import collect_values
from repo_viz.indicators.registry import evaluate, write_results
from repo_viz.indicators.spec import EvaluationContext, load_config
from repo_viz.snapshot import build_snapshot, write_snapshot


def collect_metrics(
    repo: Path,
    out_dir: Path,
    config: Path,
    *,
    trigger: str = "render",
    days: int = 30,
) -> dict[str, Any]:
    """Run the full static collection pipeline and return artifact locations."""
    if trigger not in {"render", "change"}:
        raise ValueError("trigger must be render or change")
    out_dir.mkdir(parents=True, exist_ok=True)
    graph_path = out_dir / "graph.json"
    results_path = out_dir / "indicators.json"
    snapshot = build_snapshot(repo, days=days)
    write_snapshot(snapshot, graph_path)
    values = collect_values(repo, list_python_files(repo), days=days)
    context = EvaluationContext(graph=snapshot, trigger=trigger, values=values)
    results = evaluate(load_config(config), context)
    write_results(results, results_path)
    return {
        "schema": snapshot.schema,
        "graph": str(graph_path),
        "indicators": str(results_path),
        "results": len(results),
        "trigger": trigger,
    }
