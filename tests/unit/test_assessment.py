"""Unit tests for antipattern detection, calibrated Cost/Blast/Squeeze calculation, and repo assessment."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from repo_viz.assessment import (
    Antipattern,
    RefactoringCandidate,
    RefactorTier,
    RepoAssessment,
    assign_tier,
    compute_blast_radius,
    compute_change_cost,
    compute_roi,
    compute_squeeze,
    compute_squeeze_breakdown,
    detect_antipatterns,
    write_assessment,
    write_csv_ledger,
)
from repo_viz.audit import AuditFinding
from repo_viz.indicators.spec import State
from repo_viz.model import Metrics, Node, NodeKind


def test_compute_change_cost_and_blast_radius() -> None:
    small_metrics = Metrics(loc=50, complexity=2, cognitive_complexity=2, fan_in=0, fan_out=0, churn_30d=0)
    cost = compute_change_cost(small_metrics)
    assert cost >= 1.0

    node = Node(id="src/auth.py", label="auth", kind=NodeKind.FILE, parent=".", metrics=small_metrics)
    blast = compute_blast_radius(node, small_metrics)
    # File multiplier is 1.4, base caller risk is 1.0 -> 1.4
    assert blast == 1.4

    # High fan-in node increases blast radius significantly
    popular_metrics = Metrics(loc=50, complexity=2, cognitive_complexity=2, fan_in=10, fan_out=5, churn_30d=2)
    pop_node = Node(id="src/core.py", label="core", kind=NodeKind.FILE, parent=".", metrics=popular_metrics)
    pop_blast = compute_blast_radius(pop_node, popular_metrics)
    assert pop_blast > blast
    assert pop_blast == 6.65


def test_compute_squeeze_breakdown_caps_hygiene_noise() -> None:
    # 10 hygiene findings should be capped to 4.0 points maximum
    hygiene_findings = [
        AuditFinding(
            indicator_id="hygiene",
            state=State.PARTIAL,
            severity="medium",
            value="untyped",
            evidence="missing annotations",
            action="add types",
        )
        for _ in range(10)
    ]
    clean_metrics = Metrics(cognitive_complexity=2, churn_30d=0)
    total, struct, hyg = compute_squeeze_breakdown(hygiene_findings, clean_metrics)
    assert hyg == 4.0
    assert struct == 0.0
    assert total == 4.0


def test_compute_squeeze_rewards_structural_debt_and_friction() -> None:
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
            indicator_id="sentinel",
            state=State.VIOLATION,
            severity="high",
            value="god_class",
            evidence="god class",
            action="break class",
        ),
    ]
    complex_metrics = Metrics(cognitive_complexity=15, churn_30d=3)
    total, struct, hyg = compute_squeeze_breakdown(findings, complex_metrics)
    # Boundary (20.0) + Sentinel (15.0) + Cognitive ((15 - 5) * 0.8 = 8.0) + Friction (15*3 = 45 >= 20 -> +10.0) = 53.0
    assert struct == 53.0
    assert hyg == 0.0
    assert total == 53.0
    assert compute_squeeze(findings, complex_metrics) == 53.0


def test_assign_tier_buckets_candidates_correctly() -> None:
    # Tier C: Pure hygiene/satd noise
    assert (
        assign_tier(
            squeeze=4.0,
            structural_squeeze=0.0,
            change_cost=1.5,
            blast_radius=1.5,
            roi=13.33,
            antipatterns=[Antipattern.HYGIENE_ROT],
        )
        == RefactorTier.TIER_C
    )

    # Tier A: High structural squeeze, low blast radius, high ROI
    assert (
        assign_tier(
            squeeze=45.0,
            structural_squeeze=45.0,
            change_cost=2.0,
            blast_radius=2.0,
            roi=112.5,
            antipatterns=[Antipattern.BOUNDARY_LEAK],
        )
        == RefactorTier.TIER_A
    )

    # Tier B: High structural squeeze but high blast radius (architectural migration)
    assert (
        assign_tier(
            squeeze=45.0,
            structural_squeeze=45.0,
            change_cost=3.0,
            blast_radius=6.0,
            roi=50.0,
            antipatterns=[Antipattern.COUPLING_HUB],
        )
        == RefactorTier.TIER_B
    )

    # Tier D: High cost, negligible structural payoff
    assert (
        assign_tier(
            squeeze=8.0,
            structural_squeeze=8.0,
            change_cost=10.0,
            blast_radius=5.0,
            roi=5.33,
            antipatterns=[Antipattern.GOD_COMPONENT],
        )
        == RefactorTier.TIER_D
    )


def test_compute_roi_returns_scaled_ratio() -> None:
    assert compute_roi(0.0, 2.0, 2.0) == 0.0
    assert compute_roi(20.0, 0.0, 0.0) == 0.0
    # squeeze=40.0, cost=2.0, radius=2.0 -> (40 / 4) * 10 = 100.0
    assert compute_roi(40.0, 2.0, 2.0) == 100.0


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


def test_detect_antipatterns_identifies_di_and_global_state_coupling() -> None:
    coupled_node = Node(
        id="src/legacy.py::Manager",
        label="Manager",
        kind=NodeKind.SYMBOL,
        parent="src/legacy.py",
        tags=frozenset({"global_state", "uninjected_dependency", "tight_coupling"}),
        metrics=Metrics(loc=80, complexity=5),
    )
    patterns = detect_antipatterns(coupled_node, [])
    assert Antipattern.GLOBAL_STATE in patterns
    assert Antipattern.UNINJECTED_DEPENDENCY in patterns
    assert Antipattern.TIGHT_COUPLING in patterns


def test_repo_assessment_serialization_and_ledger(tmp_path: Path) -> None:
    candidate = RefactoringCandidate(
        node_id="src/module.py",
        node_label="module",
        path="src/module.py",
        kind="file",
        change_cost=2.0,
        blast_radius=2.0,
        lift=4.0,
        squeeze=30.0,
        structural_squeeze=30.0,
        hygiene_squeeze=0.0,
        roi=75.0,
        tier=RefactorTier.TIER_A,
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
        total_change_cost=2.0,
        total_blast_radius=2.0,
        total_squeeze=30.0,
        average_roi=75.0,
        tier_counts={RefactorTier.TIER_A.value: 1},
        antipattern_counts={Antipattern.COGNITIVE_HOTSPOT: 1},
        candidates=(candidate,),
    )

    out_json = tmp_path / "assessment.json"
    write_assessment(assessment.to_dict(), out_json)
    assert out_json.is_file()

    loaded = json.loads(out_json.read_text(encoding="utf-8"))
    assert loaded["repo_name"] == "demo-repo"
    assert loaded["candidates"][0]["tier"] == "tier_a"
    assert loaded["schema"] == "repo-viz/assessment@2"

    out_csv = tmp_path / "ledger.csv"
    write_csv_ledger([candidate.to_dict()], out_csv)
    assert out_csv.is_file()

    with out_csv.open("r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 1
        assert reader[0]["tier"] == "tier_a"
        assert reader[0]["node_id"] == "src/module.py"
