"""Versioned graph snapshot specification for repo-viz.

## Specification Map

- ``SCHEMA_VERSION`` — the only accepted snapshot schema identifier.
- ``Node`` — a membrane, file, class or function with metrics and status strip.
- ``Edge`` — an interaction between two nodes with one or more visualization tracks.
- ``Port`` — an aggregated boundary crossing on a specific membrane wall.
- ``GraphSnapshot`` — the immutable, regenerated artifact consumed by the viewer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "repo-viz/graph@1"
ROOT_ID = "."
RESERVED_ARC = (315.0, 45.0)  # status strip owns this wrapped arc; ports use the remaining 290 degrees


class NodeKind(StrEnum):
    MEMBRANE = "membrane"
    FILE = "file"
    SYMBOL = "symbol"


class EdgeKind(StrEnum):
    AGGREGATE = "aggregate"
    IMPORT = "import"
    CALL = "call"
    INHERIT = "inherit"
    HTTP = "http"
    EVENT = "event"
    DB = "db"
    SECRET = "secret"
    EXEC = "exec"


class Track(StrEnum):
    DATA = "data"
    CONTROL = "control"
    SECURITY = "security"


class StatusSlot(StrEnum):
    SECURITY = "security"
    BOUNDARY = "boundary"
    EFFICIENCY = "efficiency"
    HYGIENE = "hygiene"
    SENTINEL = "sentinel"


class StatusState(StrEnum):
    VERIFIED = "verified"
    NOT_APPLICABLE = "na"
    PARTIAL = "partial"
    VIOLATION = "violation"


@dataclass(frozen=True, slots=True)
class Metrics:
    """Quantities computed statically; coverage is filled in only by an on-demand audit."""

    complexity: int = 0
    loc: int = 0
    fan_in: int = 0
    fan_out: int = 0
    churn_30d: int = 0
    coverage: float | None = None

    def __post_init__(self) -> None:
        for name in ("complexity", "loc", "fan_in", "fan_out", "churn_30d"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.coverage is not None and not 0.0 <= self.coverage <= 1.0:
            raise ValueError("coverage must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class StatusStrip:
    """Five fixed slots along a reserved perimeter arc; silent means not applicable."""

    security: StatusState = StatusState.NOT_APPLICABLE
    boundary: StatusState = StatusState.NOT_APPLICABLE
    efficiency: StatusState = StatusState.NOT_APPLICABLE
    hygiene: StatusState = StatusState.NOT_APPLICABLE
    sentinel: StatusState = StatusState.NOT_APPLICABLE
    arc_start_deg: float = RESERVED_ARC[0]
    arc_end_deg: float = RESERVED_ARC[1]

    def __post_init__(self) -> None:
        span = (self.arc_end_deg - self.arc_start_deg) % 360
        if span > 90:
            raise ValueError("status arc must occupy at most 90 degrees")
        for slot in StatusSlot:
            if not isinstance(getattr(self, slot.value), StatusState):
                raise ValueError(f"slot {slot.value} must be a StatusState")


@dataclass(frozen=True, slots=True)
class Node:
    """A container or leaf in the membrane hierarchy."""

    id: str
    label: str
    kind: NodeKind
    parent: str | None = None
    lod_rank: int = 0
    path: str | None = None
    tags: frozenset[str] = frozenset()
    metrics: Metrics = field(default_factory=Metrics)
    status: StatusStrip = field(default_factory=StatusStrip)

    def __post_init__(self) -> None:
        if not self.id or not self.label:
            raise ValueError("node id and label must be non-empty")
        if not 0 <= self.lod_rank <= 4:
            raise ValueError("lod_rank must be between 0 and 4")
        if self.id != ROOT_ID and self.parent is None:
            raise ValueError("only the root node may have no parent")


@dataclass(frozen=True, slots=True)
class Edge:
    """An interaction; ``tracks`` is a set because a DB call is both data and security."""

    source: str
    target: str
    kind: EdgeKind
    tracks: frozenset[Track] = frozenset({Track.CONTROL})
    weight: int = 1
    line: int = 0

    def __post_init__(self) -> None:
        if self.source == self.target:
            raise ValueError("self edges are not recorded")
        if self.weight < 0:
            raise ValueError("weight must be non-negative")
        if not self.tracks:
            raise ValueError("an edge must have at least one track")


@dataclass(frozen=True, slots=True)
class Port:
    """A counted crossing on membrane ``membrane`` facing ``peer``."""

    membrane: str
    peer: str
    direction: str  # "in" or "out"
    kind: EdgeKind
    tracks: frozenset[Track]
    count: int
    weight: int

    def __post_init__(self) -> None:
        if self.direction not in {"in", "out"}:
            raise ValueError("direction must be in or out")
        if self.count <= 0:
            raise ValueError("count must be positive")


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (list, tuple, set, frozenset)):
        return sorted((_jsonable(item) for item in value), key=str)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class GraphSnapshot:
    """The derived artifact. Regenerate it; never hand-edit it."""

    source_repo: str
    source_commit: str
    analyzed_at: str
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    ports: tuple[Port, ...]
    schema: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema {self.schema!r}; expected {SCHEMA_VERSION}")
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate node id")
        known = set(ids)
        for edge in self.edges:
            if edge.source not in known or edge.target not in known:
                raise ValueError(f"edge references unknown node: {edge.source} -> {edge.target}")
        for port in self.ports:
            if port.membrane not in known or port.peer not in known:
                raise ValueError("port references unknown node")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready mapping (enums as strings, tag sets as lists)."""
        return _jsonable(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GraphSnapshot:
        """Rebuild a snapshot from its JSON form, including nested dataclasses."""
        nodes = tuple(
            Node(
                id=raw["id"],
                label=raw["label"],
                kind=NodeKind(raw["kind"]),
                parent=raw.get("parent"),
                lod_rank=raw["lod_rank"],
                path=raw.get("path"),
                tags=frozenset(raw.get("tags", [])),
                metrics=Metrics(**raw["metrics"]),
                status=StatusStrip(
                    security=StatusState(raw["status"]["security"]),
                    boundary=StatusState(raw["status"]["boundary"]),
                    efficiency=StatusState(raw["status"]["efficiency"]),
                    hygiene=StatusState(raw["status"]["hygiene"]),
                    sentinel=StatusState(raw["status"]["sentinel"]),
                    arc_start_deg=raw["status"]["arc_start_deg"],
                    arc_end_deg=raw["status"]["arc_end_deg"],
                ),
            )
            for raw in data["nodes"]
        )
        edges = tuple(
            Edge(
                source=raw["source"],
                target=raw["target"],
                kind=EdgeKind(raw["kind"]),
                tracks=frozenset(Track(item) for item in raw["tracks"]),
                weight=raw["weight"],
                line=raw.get("line", 0),
            )
            for raw in data["edges"]
        )
        ports = tuple(
            Port(
                membrane=raw["membrane"],
                peer=raw["peer"],
                direction=raw["direction"],
                kind=EdgeKind(raw["kind"]),
                tracks=frozenset(Track(item) for item in raw["tracks"]),
                count=raw["count"],
                weight=raw["weight"],
            )
            for raw in data["ports"]
        )
        return cls(
            source_repo=data["source_repo"],
            source_commit=data["source_commit"],
            analyzed_at=data["analyzed_at"],
            nodes=nodes,
            edges=edges,
            ports=ports,
            schema=data.get("schema", SCHEMA_VERSION),
        )
