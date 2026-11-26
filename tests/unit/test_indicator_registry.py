"""The registry resolves callables and produces one result per node and slot."""

from __future__ import annotations

from repo_viz.indicators.registry import by_node, evaluate, resolve, results_to_dict, validate_results
from repo_viz.indicators.spec import Arc, EvaluationContext, Indicator, IndicatorConfig, State
from repo_viz.model import GraphSnapshot, Metrics, Node, NodeKind

COLORS = dict.fromkeys(State, "#000000")


def _config() -> IndicatorConfig:
    return IndicatorConfig(
        1,
        Arc(315, 45, 12, 320),
        (
            Indicator("security", "Security", "shield", 0, COLORS, "repo_viz.indicators.builtin:security"),
            Indicator(
                "coverage", "Coverage", "gauge", 1, COLORS, "repo_viz.indicators.builtin:coverage", enabled=False
            ),
        ),
    )


def test_resolve_returns_callable() -> None:
    assert callable(resolve("repo_viz.indicators.builtin:security"))


def test_evaluate_runs_only_enabled_indicators() -> None:
    node = Node(
        id="a.py",
        label="a.py",
        kind=NodeKind.FILE,
        parent=".",
        lod_rank=3,
        path="a.py",
        tags=frozenset({"secret"}),
        metrics=Metrics(complexity=4),
    )
    graph = GraphSnapshot("r", "", "", (node,), (), ())
    results = evaluate(_config(), EvaluationContext(graph=graph, trigger="render"))
    assert len(results) == 1
    assert results[0].indicator_id == "security"
    assert results[0].state is State.VIOLATION
    assert by_node(results)["a.py"][0] is results[0]
    assert results_to_dict(results)["results"][0]["state"] == "violation"


def test_validate_results_checks_version_and_rows() -> None:
    row = {
        "indicator_id": "security",
        "node_id": "a.py",
        "trigger": "render",
        "state": "partial",
        "value": 1,
        "evidence": "marker",
        "computed_at": "now",
    }
    assert validate_results({"version": 1, "results": [row]})["ok"] is True
    report = validate_results({"version": 2, "results": [{"indicator_id": "x"}]})
    assert report["ok"] is False
    assert len(report["problems"]) >= 2


def test_snapshot_round_trip() -> None:
    node = Node(id=".", label="r", kind=NodeKind.MEMBRANE)
    snapshot = GraphSnapshot("r", "sha", "now", (node,), (), ())
    assert GraphSnapshot.from_dict(snapshot.to_dict()).to_dict() == snapshot.to_dict()
