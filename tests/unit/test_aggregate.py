"""Every membrane wall crossed by a leaf edge gets a counted port."""

from __future__ import annotations

from repo_viz.aggregate import aggregate, ancestor_chain, lca_index
from repo_viz.model import Edge, EdgeKind, Node, NodeKind, Track


def _nodes() -> tuple[Node, ...]:
    return (
        Node(id=".", label="repo", kind=NodeKind.MEMBRANE),
        Node(id="pkg_a", label="a", kind=NodeKind.MEMBRANE, parent=".", lod_rank=1),
        Node(id="pkg_a/sub", label="sub", kind=NodeKind.MEMBRANE, parent="pkg_a", lod_rank=2),
        Node(id="pkg_a/sub/x.py", label="x.py", kind=NodeKind.FILE, parent="pkg_a/sub", lod_rank=3),
        Node(id="pkg_b", label="b", kind=NodeKind.MEMBRANE, parent=".", lod_rank=1),
        Node(id="pkg_b/sub", label="sub", kind=NodeKind.MEMBRANE, parent="pkg_b", lod_rank=2),
        Node(id="pkg_b/sub/y.py", label="y.py", kind=NodeKind.FILE, parent="pkg_b/sub", lod_rank=3),
    )


def test_ancestor_chain_and_lca() -> None:
    parents = {node.id: node.parent for node in _nodes()}
    left = ancestor_chain("pkg_a/sub/x.py", parents)
    right = ancestor_chain("pkg_b/sub/y.py", parents)
    assert left == (".", "pkg_a", "pkg_a/sub", "pkg_a/sub/x.py")
    assert lca_index(left, right) == 1


def test_cross_boundary_edge_counts_ports_on_every_wall() -> None:
    edge = Edge(
        source="pkg_a/sub/x.py",
        target="pkg_b/sub/y.py",
        kind=EdgeKind.CALL,
        tracks=frozenset({Track.CONTROL}),
        weight=2,
    )
    result = aggregate(_nodes(), (edge,))

    assert any(item.source == "pkg_a" and item.target == "pkg_b" and item.weight == 2 for item in result.edges)
    outward = [item for item in result.ports if item.membrane == "pkg_a" and item.peer == "."]
    assert len(outward) == 1
    assert outward[0].direction == "out"
    assert outward[0].count == 1

    inward = [item for item in result.ports if item.membrane == "pkg_b" and item.peer == "."]
    assert len(inward) == 1
    assert inward[0].direction == "in"

    deepest = [item for item in result.ports if item.membrane == "pkg_a/sub"]
    assert len(deepest) == 2
