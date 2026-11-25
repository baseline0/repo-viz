"""Built-in evaluators return explicit states, never implicit passes."""

from __future__ import annotations

from repo_viz.indicators.builtin import churn, complexity, coverage, hygiene, security, sentinel
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
