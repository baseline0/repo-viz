"""Built-in evaluators return explicit states, never implicit passes."""

from __future__ import annotations

from repo_viz.indicators.builtin import (
    churn,
    code_health,
    complexity,
    coupling,
    coverage,
    hotspot,
    hygiene,
    satd,
    security,
    sentinel,
)
from repo_viz.indicators.spec import EvaluationContext, State
from repo_viz.model import Metrics, Node, NodeKind


def _node(**kwargs: object) -> Node:
    defaults: dict[str, object] = {
        "id": "pkg/file.py",
        "label": "file.py",
        "kind": NodeKind.FILE,
        "parent": "pkg",
        "lod_rank": 3,
        "path": "pkg/file.py",
    }
    defaults.update(kwargs)
    return Node(**defaults)  # type: ignore[arg-type]


def _context(**kwargs: object) -> EvaluationContext:
    from repo_viz.model import GraphSnapshot

    graph = GraphSnapshot("r", "", "", (_node(),), (), ())
    defaults: dict[str, object] = {"graph": graph, "trigger": "render"}
    defaults.update(kwargs)
    return EvaluationContext(**defaults)  # type: ignore[arg-type]


def test_security_uses_explicit_tags() -> None:
    assert security(_node(tags=frozenset({"secret"})), _context()).state is State.VIOLATION
    assert security(_node(tags=frozenset({"egress:http"})), _context()).state is State.PARTIAL
    assert security(_node(), _context()).state is State.NA


def test_complexity_thresholds() -> None:
    assert complexity(_node(metrics=Metrics(complexity=16)), _context()).state is State.VIOLATION
    assert complexity(_node(metrics=Metrics(complexity=12)), _context()).state is State.PARTIAL
    assert complexity(_node(metrics=Metrics(complexity=4)), _context()).state is State.VERIFIED
    assert complexity(_node(), _context()).state is State.NA


def test_hygiene_and_sentinel_distinguish_absence_from_pass() -> None:
    assert hygiene(_node(tags=frozenset({"untyped"})), _context()).state is State.PARTIAL
    assert hygiene(_node(tags=frozenset({"typed"})), _context()).state is State.VERIFIED
    assert hygiene(_node(), _context()).state is State.NA
    assert sentinel(_node(tags=frozenset({"god_class"})), _context()).state is State.VIOLATION
    assert sentinel(_node(), _context()).state is State.NA


def test_coverage_is_na_without_data() -> None:
    assert coverage(_node(), _context()).state is State.NA
    assert coverage(_node(), _context(coverage={"pkg/file.py": 0.9})).state is State.VERIFIED
    assert coverage(_node(), _context(coverage={"pkg/file.py": 0.2})).state is State.VIOLATION


def test_churn_respects_change_set() -> None:
    context = _context(trigger="change", changed_paths=("other.py",))
    assert churn(_node(metrics=Metrics(churn_30d=50)), context).state is State.NA
    context = _context(trigger="change", changed_paths=("pkg/file.py",))
    assert churn(_node(metrics=Metrics(churn_30d=50)), context).state is State.VIOLATION


def test_threshold_boundary_is_inclusive() -> None:
    node = _node(metrics=Metrics(complexity=10))
    assert complexity(node, _context()).state is State.PARTIAL
    assert complexity(_node(metrics=Metrics(complexity=15)), _context()).state is State.VIOLATION
    health = _node()
    assert code_health(health, _context(values={"code_health": {"pkg/file.py": 7.1}})).state is State.PARTIAL


def test_literature_slots_return_na_without_producers() -> None:
    node = _node()
    assert satd(node, _context()).state is State.NA
    assert code_health(node, _context()).state is State.NA
    assert coupling(node, _context()).state is State.NA
    assert hotspot(node, _context()).state is State.NA


def test_producer_values_and_context_thresholds() -> None:
    node = _node()
    assert satd(node, _context(values={"satd": {"pkg/file.py": 4}})).state is State.VIOLATION
    assert satd(node, _context(values={"satd": {"pkg/file.py": 4}}, thresholds={"violation": 9})).state is State.PARTIAL
    assert code_health(node, _context(values={"code_health": {"pkg/file.py": 5.5}})).state is State.PARTIAL
    assert code_health(node, _context(values={"code_health": {"pkg/file.py": 7.5}})).state is State.VERIFIED


def test_structural_slots_use_fan_and_churn() -> None:
    node = _node(metrics=Metrics(fan_in=15, fan_out=8, churn_30d=2))
    assert coupling(node, _context()).state is State.VIOLATION
    assert hotspot(node, _context()).state is State.PARTIAL
    assert (
        complexity(_node(metrics=Metrics(complexity=12)), _context(thresholds={"partial": 20})).state is State.VERIFIED
    )
