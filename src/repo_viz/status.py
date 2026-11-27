"""Status-strip roll-up: bubble leaf evidence to every enclosing membrane.

## Specification Map

- ``status_for`` — pure rule table turning tags and complexity into five slot states.
- ``rollup_status`` — union tags/max complexity from descendants into ancestor nodes.
"""

from __future__ import annotations

from dataclasses import replace

from repo_viz.model import Node, StatusState, StatusStrip

_EFFICIENCY_VIOLATION = 15
_EFFICIENCY_PARTIAL = 10


def status_for(tags: frozenset[str], complexity: int, has_symbols: bool) -> StatusStrip:
    """Derive the five fixed slots from evidence present on a node and its descendants."""
    egress = {tag for tag in tags if tag.startswith("egress:")}
    if "secret" in tags or "egress:exec" in tags:
        security = StatusState.VIOLATION
    elif egress or ("ingress" in tags and "validated" not in tags):
        security = StatusState.PARTIAL
    elif "validated" in tags and ingress_present(tags):
        security = StatusState.VERIFIED
    else:
        security = StatusState.NOT_APPLICABLE

    if "cycle" in tags:
        boundary = StatusState.VIOLATION
    elif "private_import" in tags:
        boundary = StatusState.PARTIAL
    elif "public_only" in tags:
        boundary = StatusState.VERIFIED
    else:
        boundary = StatusState.NOT_APPLICABLE

    if complexity > _EFFICIENCY_VIOLATION:
        efficiency = StatusState.VIOLATION
    elif complexity > _EFFICIENCY_PARTIAL:
        efficiency = StatusState.PARTIAL
    elif has_symbols:
        efficiency = StatusState.VERIFIED
    else:
        efficiency = StatusState.NOT_APPLICABLE

    if "untyped" in tags:
        hygiene = StatusState.PARTIAL
    elif has_symbols:
        hygiene = StatusState.VERIFIED
    else:
        hygiene = StatusState.NOT_APPLICABLE

    if "god_class" in tags or "dead_code" in tags or "global_state" in tags or "uninjected_dependency" in tags:
        sentinel = StatusState.VIOLATION
    elif "duplicate" in tags or "tight_coupling" in tags:
        sentinel = StatusState.PARTIAL
    elif has_symbols:
        sentinel = StatusState.VERIFIED
    else:
        sentinel = StatusState.NOT_APPLICABLE

    return StatusStrip(
        security=security,
        boundary=boundary,
        efficiency=efficiency,
        hygiene=hygiene,
        sentinel=sentinel,
    )


def ingress_present(tags: frozenset[str]) -> bool:
    """Return True when a validated ingress receptor is present."""
    return "ingress" in tags


def rollup_status(nodes: tuple[Node, ...]) -> tuple[Node, ...]:
    """Union tags and maximum complexity down the ancestor chain, then set status strips."""
    parents = {node.id: node.parent for node in nodes}
    tags: dict[str, set[str]] = {node.id: set(node.tags) for node in nodes}
    complexity: dict[str, int] = {node.id: node.metrics.complexity for node in nodes}
    has_symbols: dict[str, bool] = {node.id: node.kind.value == "symbol" for node in nodes}

    for node in nodes:
        current = node.parent
        seen: set[str] = set()
        while current is not None and current not in seen:
            seen.add(current)
            tags[current].update(node.tags)
            complexity[current] = max(complexity[current], node.metrics.complexity)
            has_symbols[current] = has_symbols[current] or node.kind.value == "symbol"
            current = parents.get(current)

    result: list[Node] = []
    for node in nodes:
        strip = status_for(frozenset(tags[node.id]), complexity[node.id], has_symbols[node.id])
        # Preserve an explicit arc if one was supplied by the caller.
        strip = replace(
            strip,
            arc_start_deg=node.status.arc_start_deg,
            arc_end_deg=node.status.arc_end_deg,
        )
        result.append(replace(node, tags=frozenset(tags[node.id]), status=strip))
    return tuple(result)
