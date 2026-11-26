"""End-to-end CLI checks against a temporary git checkout.

These use the filesystem and git but no network, GPU, or sibling fleet repo.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from repo_viz.cli import app
from repo_viz.constants import REPO_ROOT

FIXTURE_CONFIG = REPO_ROOT / "tests" / "fixtures" / "indicators.toml"


def test_analyze_writes_a_versioned_snapshot(tmp_repo: Path, cli_runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "graph.json"
    result = cli_runner.invoke(app, ["analyze", "--repo", str(tmp_repo), "--out", str(out)])

    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema"] == "repo-viz/graph@1"
    assert any(node["id"] == "pkg/api.py" for node in payload["nodes"])


def test_indicators_use_the_repo_producer(tmp_repo: Path, cli_runner: CliRunner, tmp_path: Path) -> None:
    graph = tmp_path / "graph.json"
    results = tmp_path / "indicators.json"
    assert cli_runner.invoke(app, ["analyze", "--repo", str(tmp_repo), "--out", str(graph)]).exit_code == 0

    invoked = cli_runner.invoke(
        app,
        [
            "evaluate-indicators",
            "--snapshot",
            str(graph),
            "--config",
            str(FIXTURE_CONFIG),
            "--out",
            str(results),
            "--trigger",
            "render",
            "--repo",
            str(tmp_repo),
        ],
    )
    assert invoked.exit_code == 0, invoked.output
    payload = json.loads(results.read_text(encoding="utf-8"))
    satd = [row for row in payload["results"] if row["indicator_id"] == "satd"]
    assert satd
    assert any(row["state"] == "partial" and row["value"] == 1 for row in satd)


def test_summary_prints_counts(tmp_repo: Path, cli_runner: CliRunner, tmp_path: Path) -> None:
    graph = tmp_path / "graph.json"
    assert cli_runner.invoke(app, ["analyze", "--repo", str(tmp_repo), "--out", str(graph), "--json"]).exit_code == 0
    result = cli_runner.invoke(app, ["summary", "--snapshot", str(graph), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["nodes"] > 0
    assert payload["edges"] >= 0


def test_check_indicators_resolves_compute_targets() -> None:
    result = CliRunner().invoke(app, ["check-indicators", "--json"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert report["ok"] is True
    assert report["enabled"] >= 8
