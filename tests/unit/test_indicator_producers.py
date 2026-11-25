"""SATD producer and file-level inheritance are hermetic and explicit."""

from __future__ import annotations

from repo_viz.indicators.builtin import hotspot, satd
from repo_viz.indicators.producers import satd_from_source
from repo_viz.indicators.spec import EvaluationContext, State
from repo_viz.model import GraphSnapshot, Metrics, Node, NodeKind


def test_satd_counts_comments_but_not_strings() -> None:
    source = """\
# TODO: fix this
text = "FIXME: not a comment"

def f() -> None:  # HACK and XXX
    pass
"""
    assert satd_from_source(source) == 3


def test_symbols_inherit_file_churn_for_hotspot() -> None:
    file_node = Node(
        id="pkg/file.py",
        label="file.py",
        kind=NodeKind.FILE,
        parent="pkg",
        lod_rank=3,
        path="pkg/file.py",
        metrics=Metrics(churn_30d=3),
    )
    symbol = Node(
        id="pkg/file.py::busy",
        label="busy",
        kind=NodeKind.SYMBOL,
        parent="pkg/file.py",
        lod_rank=4,
        metrics=Metrics(fan_in=3, fan_out=2),
    )
    graph = GraphSnapshot("r", "", "", (file_node, symbol), (), ())
    context = EvaluationContext(graph=graph, trigger="render", thresholds={"partial": 6, "violation": 12})
    assert hotspot(symbol, context).value == 15
    assert hotspot(symbol, context).state is State.VIOLATION


def test_single_debt_marker_is_a_partial_signal() -> None:
    node = Node(
        id="pkg/file.py",
        label="file.py",
        kind=NodeKind.FILE,
        parent="pkg",
        lod_rank=3,
        path="pkg/file.py",
    )
    graph = GraphSnapshot("r", "", "", (node,), (), ())
    context = EvaluationContext(graph=graph, trigger="render", values={"satd": {"pkg/file.py": 1}})
    assert satd(node, context).state is State.PARTIAL


def test_satd_uses_file_path_for_symbol_nodes() -> None:
    file_node = Node(
        id="pkg/file.py",
        label="file.py",
        kind=NodeKind.FILE,
        parent="pkg",
        lod_rank=3,
        path="pkg/file.py",
    )
    symbol = Node(id="pkg/file.py::f", label="f", kind=NodeKind.SYMBOL, parent="pkg/file.py", lod_rank=4)
    graph = GraphSnapshot("r", "", "", (file_node, symbol), (), ())
    context = EvaluationContext(graph=graph, trigger="render", values={"satd": {"pkg/file.py": 2}})
    assert satd(symbol, context).state is State.PARTIAL
