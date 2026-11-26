"""Deterministic, component-scoped audit reports from an existing snapshot and indicator results.

## Specification Map

- ``audit_component`` — pure function; no filesystem, network or model calls.
- ``AuditReport`` — the versioned artifact shown in the viewer and used by dispatch.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from repo_viz.indicators.spec import IndicatorResult, State
from repo_viz.model import GraphSnapshot

AUDIT_SCHEMA = "repo-viz/audit@1"

ACTIONS: dict[str, str] = {
    "security": "Review ingress/egress handlers and secret handling.",
    "boundary": "Replace private cross-boundary imports with a public interface.",
    "complexity": "Split the component around its largest decision point.",
    "hygiene": "Add the missing type annotations.",
    "sentinel": "Remove dead code or break up the oversized class.",
    "coverage": "Add tests for the uncovered paths.",
    "churn": "Investigate repeated changes and stabilise the interface.",
    "coupling": "Introduce an interface to reduce fan-in and fan-out.",
    "hotspot": "Prioritise this change hotspot for refactoring.",
    "satd": "Resolve the TODO/FIXME marker in this component.",
    "code_health": "Apply a focused code-health cleanup.",
    "arch_drift": "Reduce cross-boundary interactions from this membrane.",
    "cognitive_friction": "Flatten nested control flow in this component.",
    "cochange": "Look for a shared abstraction behind these co-changes.",
}

SEVERITY = {State.VIOLATION: "high", State.PARTIAL: "medium"}


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """One degraded indicator and its suggested action."""

    indicator_id: str
    state: State
    severity: str
    value: str | float | None
    evidence: str
    action: str


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Component audit: metrics, findings and suggested actions."""

    node_id: str
    node_label: str
    path: str | None
    source_commit: str
    metrics: dict[str, Any]
    findings: tuple[AuditFinding, ...] = field(default_factory=tuple)
    suggested_actions: tuple[str, ...] = field(default_factory=tuple)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema: str = AUDIT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready mapping."""
        payload = asdict(self)
        payload["findings"] = [
            {**item, "state": item["state"].value if isinstance(item["state"], State) else item["state"]}
            for item in payload["findings"]
        ]
        return payload


def audit_component(
    snapshot: GraphSnapshot,
    results: tuple[IndicatorResult, ...],
    node_id: str,
) -> AuditReport:
    """Build an audit for one node from already-computed evidence."""
    node = next((item for item in snapshot.nodes if item.id == node_id), None)
    if node is None:
        raise ValueError(f"unknown node: {node_id}")
    findings = tuple(
        AuditFinding(
            indicator_id=result.indicator_id,
            state=result.state,
            severity=SEVERITY.get(result.state, "low"),
            value=result.value,
            evidence=result.evidence,
            action=ACTIONS.get(result.indicator_id, "Investigate this indicator."),
        )
        for result in results
        if result.node_id == node_id and result.state in SEVERITY
    )
    actions = tuple(dict.fromkeys(finding.action for finding in findings))
    return AuditReport(
        node_id=node.id,
        node_label=node.label,
        path=node.path,
        source_commit=snapshot.source_commit,
        metrics=asdict(node.metrics),
        findings=findings,
        suggested_actions=actions,
    )


def audit_from_artifacts(snapshot_path: Path, results_path: Path, node_id: str) -> AuditReport:
    """Load two derived artifacts and audit one node; host-side but fully testable."""
    from repo_viz.indicators.registry import results_from_dict

    snapshot = GraphSnapshot.from_dict(json.loads(snapshot_path.read_text(encoding="utf-8")))
    results = results_from_dict(json.loads(results_path.read_text(encoding="utf-8")))
    return audit_component(snapshot, results, node_id)


def write_report(report: AuditReport, out_path: Path) -> None:
    """Atomically write the derived audit artifact."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_name(f".{out_path.name}.tmp")
    temporary.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, out_path)
