"""Audit reports and work-item requests are pure functions of stored evidence."""

from __future__ import annotations

from repo_viz.audit import audit_component
from repo_viz.indicators.spec import IndicatorResult, State
from repo_viz.model import GraphSnapshot, Metrics, Node, NodeKind
from repo_viz.workitem import build_work_item_payload


def _graph() -> GraphSnapshot:
    file_node = Node(
        id="pkg/a.py",
        label="a.py",
        kind=NodeKind.FILE,
        parent="pkg",
        lod_rank=3,
        path="pkg/a.py",
        metrics=Metrics(complexity=16, coverage=0.4, churn_30d=4),
    )
    return GraphSnapshot("r", "sha", "now", (file_node,), (), ())


def _results() -> tuple[IndicatorResult, ...]:
    return (
        IndicatorResult("complexity", "pkg/a.py", "render", State.VIOLATION, 16, "high", "now"),
        IndicatorResult("coverage", "pkg/a.py", "render", State.PARTIAL, 0.4, "low", "now"),
        IndicatorResult("security", "pkg/a.py", "render", State.VERIFIED, None, "ok", "now"),
    )


def test_audit_collects_only_degraded_findings() -> None:
    report = audit_component(_graph(), _results(), "pkg/a.py")
    assert [item.indicator_id for item in report.findings] == ["complexity", "coverage"]
    assert report.findings[0].severity == "high"
    assert report.findings[1].severity == "medium"
    assert len(report.suggested_actions) == 2
    assert report.metrics["complexity"] == 16


def test_work_item_payload_is_unauthorized_and_bounded() -> None:
    report = audit_component(_graph(), _results(), "pkg/a.py")
    payload = build_work_item_payload(report, snapshot="graph.json", results="indicators.json")
    assert payload["status"] == "idea"
    assert payload["repo"] == "repo-viz"
    assert payload["id"].startswith("rv-")
    assert payload["allowed_paths"] == ["pkg/a.py"]
    assert payload["gate"] is None
    assert payload["gate_hash"] is None
    assert "graph.json" in payload["evidence"]["snapshot"]
