"""Ancestor-chain port counting and LCA macro-edge bubbling.

## Specification Map

- ``ancestor_chain`` — root-to-node path used for every boundary walk.
- ``aggregate`` — converts leaf edges into per-wall port counters and macro edges.
- Port angles are deliberately NOT computed here: that is the frozen layout step.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from repo_viz.metrics import with_fan
from repo_viz.model import Edge, EdgeKind, Node, Port, Track
from repo_viz.status import rollup_status

_PortKey = tuple[str, str, str, EdgeKind, frozenset[Track]]
_MacroKey = tuple[str, str, frozenset[Track]]


@dataclass(frozen=True, slots=True)
class Aggregation:
    """The three outputs consumed by the snapshot builder."""

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    ports: tuple[Port, ...]


def ancestor_chain(node_id: str, parents: dict[str, str | None]) -> tuple[str, ...]:
    """Return the root-to-node chain, guarding against malformed parent cycles."""
    chain = [node_id]
    seen = {node_id}
    while parents.get(chain[-1]) is not None:
        parent = parents[chain[-1]]
        if parent is None or parent in seen:
            break
        chain.append(parent)
        seen.add(parent)
    return tuple(reversed(chain))


def lca_index(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    """Return the length of the longest common prefix of two ancestor chains."""
    index = 0
    for a, b in zip(left, right):
        if a != b:
            break
        index += 1
    return index


def aggregate(nodes: tuple[Node, ...], leaf_edges: Iterable[Edge]) -> Aggregation:
    """Count every membrane wall crossed by every leaf edge and emit macro edges."""
    parents = {node.id: node.parent for node in nodes}
    ports: dict[_PortKey, list[int]] = defaultdict(lambda: [0, 0])
    macros: dict[_MacroKey, int] = defaultdict(int)

    def count_port(membrane: str, peer: str, direction: str, edge: Edge) -> None:
        key = (membrane, peer, direction, edge.kind, edge.tracks)
        ports[key][0] += 1
        ports[key][1] += edge.weight

    for edge in leaf_edges:
        source_chain = ancestor_chain(edge.source, parents)
        target_chain = ancestor_chain(edge.target, parents)
        common = lca_index(source_chain, target_chain)

        # Walking from the source up to the LCA: enter each membrane from its
        # source-side child, then leave it toward its parent.
        for pos in range(common, len(source_chain) - 1):
            membrane = source_chain[pos]
            count_port(membrane, source_chain[pos + 1], "in", edge)
            if pos > 0:
                count_port(membrane, source_chain[pos - 1], "out", edge)

        # Walking from the LCA down to the target: enter from the parent
        # direction, then leave toward the target-side child.
        for pos in range(common, len(target_chain) - 1):
            membrane = target_chain[pos]
            count_port(membrane, target_chain[pos + 1], "out", edge)
            if pos > 0:
                count_port(membrane, target_chain[pos - 1], "in", edge)

        # A common prefix of one means the LCA is the repo root: the macro view
        # wants the top-level membranes, so a deep call still reads pkg_a -> pkg_b.
        def top_under(chain: tuple[str, ...]) -> str:
            if len(chain) == 1:
                return chain[0]
            if common <= 1:
                return chain[1]
            return chain[min(common + 1, len(chain) - 1)]

        source_top = top_under(source_chain)
        target_top = top_under(target_chain)
        if source_top != target_top:
            macros[(source_top, target_top, edge.tracks)] += edge.weight

    port_records = tuple(
        Port(
            membrane=key[0],
            peer=key[1],
            direction=key[2],
            kind=key[3],
            tracks=key[4],
            count=value[0],
            weight=value[1],
        )
        for key, value in sorted(ports.items(), key=lambda item: str(item[0]))
    )
    macro_edges = tuple(
        Edge(
            source=key[0],
            target=key[1],
            kind=EdgeKind.AGGREGATE,
            tracks=key[2],
            weight=weight,
        )
        for key, weight in sorted(macros.items(), key=lambda item: str(item[0]))
    )
    enriched = rollup_status(with_fan(nodes, leaf_edges))
    # Keep leaf edges in the artifact so the micro LOD can draw exact call paths;
    # macro edges are distinguishable by kind="aggregate".
    all_edges = tuple(leaf_edges) + macro_edges
    return Aggregation(nodes=enriched, edges=all_edges, ports=port_records)
