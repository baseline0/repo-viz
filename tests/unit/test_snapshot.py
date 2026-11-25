"""The pure snapshot builder is hermetic, versioned and deterministic."""

from __future__ import annotations

from repo_viz.model import SCHEMA_VERSION
from repo_viz.snapshot import build_snapshot_from_sources

SOURCES = {
    "pkg/core.py": "class Engine:\n    pass\n",
    "pkg/api.py": "from .core import Engine\n\nclass Child(Engine):\n    pass\n",
}


def test_snapshot_has_versioned_consistent_graph() -> None:
    snapshot = build_snapshot_from_sources(SOURCES, repo_label="sample", source_commit="abc")
    assert snapshot.schema == SCHEMA_VERSION
    ids = {node.id for node in snapshot.nodes}
    assert {"pkg", "pkg/core.py", "pkg/api.py", "pkg/api.py::Child"} <= ids
    assert all(edge.source in ids and edge.target in ids for edge in snapshot.edges)
    assert all(port.membrane in ids and port.peer in ids for port in snapshot.ports)


def test_snapshot_is_deterministic_for_identical_inputs() -> None:
    first = build_snapshot_from_sources(SOURCES, repo_label="sample", analyzed_at="now")
    second = build_snapshot_from_sources(SOURCES, repo_label="sample", analyzed_at="now")
    assert first.to_dict() == second.to_dict()


def test_deep_paths_duplicate_symbols_and_recursion_are_safe() -> None:
    sources = {
        "a/b/c/d/e/deep.py": "class Mock:\n    pass\n\nclass Mock:\n    def run(self):\n        self.run()\n",
        "a/b/c/d/e/other.py": "from .deep import Mock\n\nclass Child(Mock):\n    pass\n",
    }
    snapshot = build_snapshot_from_sources(sources)
    ids = [node.id for node in snapshot.nodes]
    assert len(ids) == len(set(ids))
    assert all(node.lod_rank <= 4 for node in snapshot.nodes)
    assert all(edge.source != edge.target for edge in snapshot.edges)


def test_cross_package_edge_creates_ports_and_macro_edge() -> None:
    sources = {
        "pkg_a/core.py": "def helper(): pass\n",
        "pkg_b/api.py": "from pkg_a.core import helper\n\ndef call(): helper()\n",
    }
    snapshot = build_snapshot_from_sources(sources)
    assert any(edge.source == "pkg_b" and edge.target == "pkg_a" for edge in snapshot.edges)
    assert any(port.membrane == "pkg_a" and port.direction == "out" for port in snapshot.ports)
    assert any(port.membrane == "pkg_b" and port.direction == "out" for port in snapshot.ports)
