"""Unit tests for antipattern detection, Lift/Squeeze calculation, and repo assessment."""

from __future__ import annotations

import json
from pathlib import Path

from repo_viz.assessment import (
    Antipattern,
    RefactoringCandidate,
    RepoAssessment,
    compute_lift,
    compute_roi,
    compute_squeeze,
    detect_antipatterns,
    write_assessment,
)
from repo_viz.audit import AuditFinding
from repo_viz.indicators.spec import State
from repo_viz.model import Metrics, Node, NodeKind


def test_compute_lift_scales_with_loc_coupling_and_churn() -> None:
    small_metrics = Metrics(loc=50, fan_in=0, fan_out=0, churn_30d=0)
    assert compute_lift(small_metrics) == 1.0

    large_metrics = Metrics(loc=500, fan_in=5, fan_out=10, churn_30d=10)
    lift = compute_lift(large_metrics)
    # base_loc: 10.0, coupling_factor: 1 + 0.75 + 0.5 = 2.25, churn_factor: 1 + 0.5 = 1.5 -> 10 * 2.25 * 1.5 = 33.75
    assert lift == 33.75
    assert lift > compute_lift(small_metrics)


def test_compute_squeeze_weights_findings_and_complexity() -> None:
    empty_findings: list[AuditFinding] = []
    clean_metrics = Metrics(cognitive_complexity=2, churn_30d=1)
    assert compute_squeeze(empty_findings, clean_metrics) == 0.0

    findings = [
        AuditFinding(
            indicator_id="boundary",
            state=State.VIOLATION,
            severity="high",
            value="cycle",
            evidence="cycle detected",
            action="break cycle",
        ),
        AuditFinding(
            indicator_id="hygiene",
            state=State.PARTIAL,
            severity="medium",
            value="untyped",
            evidence="missing annotations",
            action="add types",
        ),
    ]
    complex_metrics = Metrics(cognitive_complexity=15, churn_30d=3)
    # High: 15.0, Medium: 5.0, cognitive: (15 - 5) * 0.8 = 8.0, friction: 15 * 3 = 45 >= 20 -> +10.0 -> Total: 38.0
    squeeze = compute_squeeze(findings, complex_metrics)
    assert squeeze == 38.0


def test_compute_roi_returns_scaled_ratio() -> None:
    assert compute_roi(0.0, 10.0) == 0.0
    assert compute_roi(10.0, 0.0) == 0.0
    # squeeze=20.0, lift=5.0 -> (20 / 5) * 10 = 40.0
    assert compute_roi(20.0, 5.0) == 40.0


def test_detect_antipatterns_identifies_architectural_smells() -> None:
    god_node = Node(
        id="src/god.py",
        label="god",
        kind=NodeKind.FILE,
        parent=".",
        metrics=Metrics(loc=400, complexity=25, fan_in=10, fan_out=10),
    )
    findings = [
        AuditFinding(
            indicator_id="boundary",
            state=State.VIOLATION,
            severity="high",
            value="cycle",
            evidence="cycle detected",
            action="break cycle",
        ),
        AuditFinding(
            indicator_id="satd",
            state=State.PARTIAL,
            severity="medium",
            value=2,
            evidence="TODO comment",
            action="fix TODO",
        ),
    ]

    patterns = detect_antipatterns(god_node, findings)
    assert Antipattern.GOD_COMPONENT in patterns
    assert Antipattern.COUPLING_HUB in patterns
    assert Antipattern.BOUNDARY_LEAK in patterns
    assert Antipattern.SATD_DEBT in patterns


def test_repo_assessment_serialization_and_write(tmp_path: Path) -> None:
    candidate = RefactoringCandidate(
        node_id="src/module.py",
        node_label="module",
        path="src/module.py",
        kind="file",
        lift=5.0,
        squeeze=25.0,
        roi=50.0,
        antipatterns=(Antipattern.COGNITIVE_HOTSPOT,),
        suggested_actions=("flatten nested branches",),
        findings_count=1,
        metrics={"loc": 100},
    )

    assessment = RepoAssessment(
        repo_name="demo-repo",
        repo_path="/tmp/demo-repo",
        source_commit="abcd1234",
        total_nodes=10,
        degraded_nodes=1,
        clean_nodes=9,
        total_lift=5.0,
        total_squeeze=25.0,
        average_roi=50.0,
        antipattern_counts={Antipattern.COGNITIVE_HOTSPOT: 1},
        candidates=(candidate,),
    )

    out_file = tmp_path / "assessment.json"
    write_assessment(assessment.to_dict(), out_file)
    assert out_file.is_file()

    loaded = json.loads(out_file.read_text(encoding="utf-8"))
    assert loaded["repo_name"] == "demo-repo"
    assert loaded["candidates"][0]["roi"] == 50.0
    assert loaded["schema"] == "repo-viz/assessment@1"
