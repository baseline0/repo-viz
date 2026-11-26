"""Calculations for the evidence-backed indicator slots.

All tests are hermetic: mock ASTs, synthetic graphs and in-memory commit lists.
"""

from __future__ import annotations

import ast

from repo_viz.indicators.builtin import arch_drift, cochange, cognitive_friction
from repo_viz.indicators.producers import cochange_counts
from repo_viz.indicators.spec import EvaluationContext, State
from repo_viz.metrics import cognitive_complexity
from repo_viz.model import Edge, EdgeKind, GraphSnapshot, Metrics, Node, NodeKind, Track


def test_cognitive_complexity_counts_nesting() -> None:
    tree = ast.parse("def f(x):\n    if x:\n        for y in x:\n            if y:\n                pass\n")
    assert cognitive_complexity(tree.body[0]) == 6


def test_arch_drift_counts_cross_boundary_edges_for_a_membrane() -> None:
    nodes = (
        Node(id=".", label="repo", kind=NodeKind.MEMBRANE),
        Node(id="a", label="a", kind=NodeKind.MEMBRANE, parent=".", lod_rank=1),
        Node(id="a/f.py", label="f", kind=NodeKind.FILE, parent="a", lod_rank=2),
        Node(id="b", label="b", kind=NodeKind.MEMBRANE, parent=".", lod_rank=1),
        Node(id="b/g.py", label="g", kind=NodeKind.FILE, parent="b", lod_rank=2),
    )
    edges = (
        Edge(
            source="a",
            target="b",
            kind=EdgeKind.AGGREGATE,
            tracks=frozenset({Track.CONTROL}),
        ),
    )
    graph = GraphSnapshot("r", "", "", nodes, edges, ())
    context = EvaluationContext(graph=graph, trigger="render", thresholds={"partial": 5, "violation": 12})
    assert arch_drift(nodes[1], context).value == 1
    assert arch_drift(nodes[2], context).state is State.NA


def test_cognitive_friction_multiplies_complexity_by_file_churn() -> None:
    file_node = Node(
        id="pkg/f.py",
        label="f.py",
        kind=NodeKind.FILE,
        parent="pkg",
        lod_rank=3,
        path="pkg/f.py",
        metrics=Metrics(churn_30d=3),
    )
    symbol = Node(
        id="pkg/f.py::busy",
        label="busy",
        kind=NodeKind.SYMBOL,
        parent="pkg/f.py",
        lod_rank=4,
        metrics=Metrics(cognitive_complexity=4),
    )
    graph = GraphSnapshot("r", "", "", (file_node, symbol), (), ())
    context = EvaluationContext(graph=graph, trigger="render", thresholds={"partial": 8, "violation": 20})
    result = cognitive_friction(symbol, context)
    assert result.value == 12
    assert result.state is State.PARTIAL


def test_cochange_counts_pairs_from_mock_commits() -> None:
    assert cochange_counts([("a.py", "b.py"), ("b.py", "c.py")]) == {"a.py": 1, "b.py": 2, "c.py": 1}
    assert cochange_counts([("a.py", "a.py")]) == {}


def test_cochange_evaluator_requires_a_producer() -> None:
    node = Node(id="pkg/f.py", label="f.py", kind=NodeKind.FILE, parent="pkg", lod_rank=3, path="pkg/f.py")
    graph = GraphSnapshot("r", "", "", (node,), (), ())
    empty = EvaluationContext(graph=graph, trigger="render")
    assert cochange(node, empty).state is State.NA
    produced = EvaluationContext(
        graph=graph,
        trigger="render",
        values={"cochange": {"pkg/f.py": 6}},
        thresholds={"partial": 2, "violation": 5},
    )
    assert cochange(node, produced).state is State.VIOLATION
