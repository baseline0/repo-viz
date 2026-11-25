"""Declarative indicator-slot specification and TOML config loader.

## Specification Map

- ``Indicator`` — a visual slot bound to a dotted evaluator function.
- ``IndicatorConfig`` — the parsed, validated configuration file.
- ``Evaluation`` / ``IndicatorResult`` — evaluator output and its stored form.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from repo_viz.model import GraphSnapshot

VALID_TRIGGERS = frozenset({"render", "change"})
VALID_GLYPHS = frozenset({"shield", "gate", "bolt", "check", "bug", "gauge", "clock", "dot"})


class State(StrEnum):
    VERIFIED = "verified"
    NA = "na"
    PARTIAL = "partial"
    VIOLATION = "violation"


@dataclass(frozen=True, slots=True)
class Arc:
    """Reserved compass arc; at most 90 degrees, leaving the rest for ports."""

    start_deg: float
    end_deg: float
    step_deg: float
    first_deg: float

    def __post_init__(self) -> None:
        if (self.end_deg - self.start_deg) % 360 > 90:
            raise ValueError("indicator arc must occupy at most 90 degrees")
        if self.step_deg <= 0:
            raise ValueError("step_deg must be positive")

    def degrees(self, position: int) -> float:
        """Compass angle for a slot position."""
        return (self.first_deg + position * self.step_deg) % 360


@dataclass(frozen=True, slots=True)
class Indicator:
    id: str
    label: str
    glyph: str
    position: int
    colors: Mapping[State, str]
    compute: str
    enabled: bool = True
    triggers: frozenset[str] = frozenset(VALID_TRIGGERS)
    timeout_seconds: int = 5
    thresholds: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id or ":" not in self.compute:
            raise ValueError("indicator needs an id and a module:function compute reference")
        if self.glyph not in VALID_GLYPHS:
            raise ValueError(f"unknown glyph {self.glyph!r}")
        if self.position < 0:
            raise ValueError("position must be non-negative")
        if not set(self.triggers) <= VALID_TRIGGERS:
            raise ValueError("trigger must be render or change")
        missing = set(State) - set(self.colors)
        if missing:
            raise ValueError(f"indicator {self.id} missing colors for {sorted(missing)}")
        if self.timeout_seconds < 0:
            raise ValueError("timeout_seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class IndicatorConfig:
    version: int
    arc: Arc
    indicators: tuple[Indicator, ...]

    def __post_init__(self) -> None:
        ids = [item.id for item in self.indicators]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate indicator id")
        positions = [item.position for item in self.indicators]
        if len(positions) != len(set(positions)):
            raise ValueError("duplicate indicator position")

    def enabled_for(self, trigger: str) -> tuple[Indicator, ...]:
        """Return enabled indicators that run for ``trigger``, in slot order."""
        return tuple(
            sorted(
                (item for item in self.indicators if item.enabled and trigger in item.triggers),
                key=lambda item: item.position,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready mapping for the viewer."""
        return {
            "version": self.version,
            "arc": {
                "start_deg": self.arc.start_deg,
                "end_deg": self.arc.end_deg,
                "step_deg": self.arc.step_deg,
                "first_deg": self.arc.first_deg,
            },
            "indicators": [
                {
                    "id": item.id,
                    "label": item.label,
                    "glyph": item.glyph,
                    "position": item.position,
                    "colors": {state.value: color for state, color in item.colors.items()},
                    "enabled": item.enabled,
                    "triggers": sorted(item.triggers),
                    "thresholds": dict(item.thresholds),
                }
                for item in self.indicators
            ],
        }


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    """Everything an evaluator may read; evaluators must be pure."""

    graph: GraphSnapshot
    trigger: str
    changed_paths: tuple[str, ...] = ()
    coverage: Mapping[str, float] = field(default_factory=dict)
    values: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    thresholds: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Evaluation:
    """The result of one evaluator for one node."""

    state: State
    value: str | float | None = None
    evidence: str = ""


@dataclass(frozen=True, slots=True)
class IndicatorResult:
    """A stored evaluation, keyed by indicator, node and trigger."""

    indicator_id: str
    node_id: str
    trigger: str
    state: State
    value: str | float | None
    evidence: str
    computed_at: str


def load_config(path: Path) -> IndicatorConfig:
    """Parse and validate a TOML indicator configuration."""
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    arc_data = raw["arc"]
    arc = Arc(
        start_deg=float(arc_data["start_deg"]),
        end_deg=float(arc_data["end_deg"]),
        step_deg=float(arc_data["step_deg"]),
        first_deg=float(arc_data["first_deg"]),
    )
    indicators = tuple(
        Indicator(
            id=item["id"],
            label=item["label"],
            glyph=item["glyph"],
            position=int(item["position"]),
            colors={State(key): value for key, value in item["colors"].items()},
            compute=item["compute"],
            enabled=bool(item.get("enabled", True)),
            triggers=frozenset(item.get("triggers", VALID_TRIGGERS)),
            timeout_seconds=int(item.get("timeout_seconds", 5)),
            thresholds=dict(item.get("thresholds", {})),
        )
        for item in raw["indicators"]
    )
    return IndicatorConfig(version=int(raw["version"]), arc=arc, indicators=indicators)
