"""Model invariants reject invalid snapshots and serialize enums as strings."""

from __future__ import annotations

import pytest

from repo_viz.model import (
    SCHEMA_VERSION,
    Edge,
    EdgeKind,
    GraphSnapshot,
    Metrics,
    Node,
    NodeKind,
    Port,
    StatusState,
    StatusStrip,
    Track,
)


def test_metrics_rejects_coverage_outside_unit_interval() -> None:
    with pytest.raises(ValueError, match="coverage"):
        Metrics(coverage=1.5)


def test_status_strip_rejects_arc_over_ninety_degrees() -> None:
    with pytest.raises(ValueError, match="arc"):
        StatusStrip(arc_start_deg=0, arc_end_deg=120)


def test_non_root_node_requires_parent() -> None:
    with pytest.raises(ValueError, match="parent"):
        Node(id="file.py", label="file.py", kind=NodeKind.FILE)


def test_edge_rejects_self_reference_and_empty_tracks() -> None:
    with pytest.raises(ValueError, match="self"):
        Edge(source="a", target="a", kind=EdgeKind.CALL)
    with pytest.raises(ValueError, match="track"):
        Edge(source="a", target="b", kind=EdgeKind.CALL, tracks=frozenset())


def test_snapshot_rejects_duplicate_ids_and_dangling_edges() -> None:
    node = Node(id="a", label="a", kind=NodeKind.MEMBRANE, parent=".")
    with pytest.raises(ValueError, match="duplicate"):
        GraphSnapshot("r", "", "", (node, node), (), (), SCHEMA_VERSION)
    edge = Edge(source="a", target="missing", kind=EdgeKind.CALL)
    with pytest.raises(ValueError, match="unknown node"):
        GraphSnapshot("r", "", "", (node,), (edge,), (), SCHEMA_VERSION)


def test_snapshot_serializes_enums_and_tag_sets() -> None:
    node = Node(id="a", label="a", kind=NodeKind.MEMBRANE, parent=".", tags=frozenset({"package"}))
    port = Port(
        membrane="a",
        peer="b",
        direction="out",
        kind=EdgeKind.AGGREGATE,
        tracks=frozenset({Track.DATA}),
        count=1,
        weight=1,
    )
    peer = Node(id="b", label="b", kind=NodeKind.MEMBRANE, parent=".")
    snapshot = GraphSnapshot("r", "sha", "now", (node, peer), (), (port,))
    payload = snapshot.to_dict()
    assert payload["nodes"][0]["kind"] == "membrane"
    assert payload["nodes"][0]["tags"] == ["package"]
    assert payload["ports"][0]["tracks"] == ["data"]
    assert payload["nodes"][0]["status"]["security"] == StatusState.NOT_APPLICABLE.value
