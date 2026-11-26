"""Antipattern detection, Lift/Squeeze calculation, and repository assessment.

## Specification Map

- ``compute_lift`` — estimate refactoring cost/effort from LOC, coupling, and churn.
- ``compute_squeeze`` — estimate refactoring dividend/value from findings and complexity.
- ``compute_roi`` — calculate payoff-to-effort ratio (squeeze / lift).
- ``detect_antipatterns`` — classify architectural and code-health smells.
- ``assess_repo`` — assess a repository and rank refactoring candidates by ROI.
- ``walk_fleet`` — assess all matching fleet and tool repositories.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from repo_viz.audit import AuditFinding, AuditReport, audit_component
from repo_viz.constants import CONFIG_DIR
from repo_viz.discovery import list_python_files
from repo_viz.indicators.producers import collect_values
from repo_viz.indicators.registry import evaluate
from repo_viz.indicators.spec import EvaluationContext, load_config
from repo_viz.model import Metrics, Node, NodeKind
from repo_viz.snapshot import build_snapshot

ASSESSMENT_SCHEMA = "repo-viz/assessment@1"
FLEET_ASSESSMENT_SCHEMA = "repo-viz/fleet-assessment@1"
DEFAULT_INDICATOR_CONFIG = CONFIG_DIR / "indicators.toml"


class Antipattern:
    GOD_COMPONENT = "god_component"
    COGNITIVE_HOTSPOT = "cognitive_hotspot"
    COUPLING_HUB = "coupling_hub"
    BOUNDARY_LEAK = "boundary_leak"
    HYGIENE_ROT = "hygiene_rot"
    SATD_DEBT = "satd_debt"
    SECURITY_SMELL = "security_smell"


def compute_lift(metrics: Metrics) -> float:
    """Calculate refactoring effort, blast radius, and risk.

    - Code size: base scale of ~1 unit per 50 LOC.
    - Blast radius: fan-in (caller breakage risk) + fan-out (dependency entanglement).
    - Volatility: recent churn multiplier.
    """
    base_loc = max(1.0, metrics.loc / 50.0)
    coupling_factor = 1.0 + (0.15 * metrics.fan_in) + (0.05 * metrics.fan_out)
    churn_factor = 1.0 + (0.05 * min(metrics.churn_30d, 20))
    return round(base_loc * coupling_factor * churn_factor, 2)


def compute_squeeze(findings: Sequence[AuditFinding], metrics: Metrics) -> float:
    """Calculate refactoring payoff, technical debt elimination, and maintainability dividend.

    - High severity violations: +15 points each.
    - Medium severity findings: +5 points each.
    - Cognitive load reduction dividend.
    - Churn x complexity friction penalty removal.
    """
    score = 0.0
    for finding in findings:
        if finding.severity == "high":
            score += 15.0
        elif finding.severity == "medium":
            score += 5.0

    if metrics.cognitive_complexity > 5:
        score += (metrics.cognitive_complexity - 5) * 0.8

    friction = metrics.cognitive_complexity * metrics.churn_30d
    if friction >= 20:
        score += 10.0
    elif friction >= 8:
        score += 4.0

    return round(max(0.0, score), 2)


def compute_roi(squeeze: float, lift: float) -> float:
    """Calculate the refactoring return on investment: squeeze / lift scaled to 10."""
    if lift <= 0.0:
        return 0.0
    return round((squeeze / lift) * 10.0, 2)


def detect_antipatterns(node: Node, findings: Sequence[AuditFinding]) -> tuple[str, ...]:
    """Identify architectural and structural antipatterns for a node."""
    patterns: list[str] = []
    metrics = node.metrics

    # God component: oversized LOC or high complexity + size
    if metrics.loc >= 350 or (metrics.loc >= 200 and metrics.complexity >= 15):
        patterns.append(Antipattern.GOD_COMPONENT)

    # Cognitive hotspot: high cognitive complexity with high churn
    if metrics.cognitive_complexity >= 15 and metrics.churn_30d >= 3:
        patterns.append(Antipattern.COGNITIVE_HOTSPOT)

    # Coupling hub: high in-and-out degrees creating architectural bottleneck
    if (metrics.fan_in + metrics.fan_out) >= 15:
        patterns.append(Antipattern.COUPLING_HUB)

    # Smells detected via findings
    finding_indicators = {f.indicator_id for f in findings}
    if "boundary" in finding_indicators or "arch_drift" in finding_indicators:
        patterns.append(Antipattern.BOUNDARY_LEAK)
    if "hygiene" in finding_indicators:
        patterns.append(Antipattern.HYGIENE_ROT)
    if "satd" in finding_indicators:
        patterns.append(Antipattern.SATD_DEBT)
    if "security" in finding_indicators:
        patterns.append(Antipattern.SECURITY_SMELL)

    return tuple(sorted(dict.fromkeys(patterns)))


@dataclass(frozen=True, slots=True)
class RefactoringCandidate:
    """A prioritized refactoring candidate with lift, squeeze, and antipattern diagnostics."""

    node_id: str
    node_label: str
    path: str | None
    kind: str
    lift: float
    squeeze: float
    roi: float
    antipatterns: tuple[str, ...]
    suggested_actions: tuple[str, ...]
    findings_count: int
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RepoAssessment:
    """Repository-wide assessment summary with ranked refactoring proposals."""

    repo_name: str
    repo_path: str
    source_commit: str
    total_nodes: int
    degraded_nodes: int
    clean_nodes: int
    total_lift: float
    total_squeeze: float
    average_roi: float
    antipattern_counts: dict[str, int]
    candidates: tuple[RefactoringCandidate, ...]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema: str = ASSESSMENT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [c.to_dict() for c in self.candidates]
        return payload


@dataclass(frozen=True, slots=True)
class FleetAssessment:
    """Fleet-wide assessment across all analyzed repositories."""

    total_repos: int
    total_candidates: int
    repo_summaries: list[dict[str, Any]]
    top_fleet_candidates: list[dict[str, Any]]
    antipattern_distribution: dict[str, int]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    schema: str = FLEET_ASSESSMENT_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_repo(
    repo_path: Path,
    *,
    days: int = 30,
    config_path: Path | None = None,
) -> RepoAssessment:
    """Run full static analysis on a repository and rank refactoring proposals by ROI."""
    repo = repo_path.resolve()
    repo_name = repo.name
    resolved_config = config_path or DEFAULT_INDICATOR_CONFIG

    snapshot = build_snapshot(repo, days=days)
    files = list_python_files(repo)
    values = collect_values(repo, files, days=days)
    context = EvaluationContext(graph=snapshot, trigger="render", values=values)
    results = evaluate(load_config(resolved_config), context)

    candidates: list[RefactoringCandidate] = []
    antipattern_counter: Counter[str] = Counter()
    degraded_node_ids: set[str] = set()

    # Analyze all concrete file and symbol nodes (skip root container '.' and external)
    for node in snapshot.nodes:
        if node.id in {".", "external"}:
            continue
        if node.kind is NodeKind.MEMBRANE and not node.path:
            continue

        report: AuditReport = audit_component(snapshot, results, node.id)
        findings = report.findings
        lift = compute_lift(node.metrics)
        squeeze = compute_squeeze(findings, node.metrics)
        roi = compute_roi(squeeze, lift)
        antipatterns = detect_antipatterns(node, findings)

        if findings or antipatterns or squeeze > 0:
            degraded_node_ids.add(node.id)
            for ap in antipatterns:
                antipattern_counter[ap] += 1

            candidates.append(
                RefactoringCandidate(
                    node_id=node.id,
                    node_label=node.label,
                    path=node.path,
                    kind=node.kind.value,
                    lift=lift,
                    squeeze=squeeze,
                    roi=roi,
                    antipatterns=antipatterns,
                    suggested_actions=report.suggested_actions,
                    findings_count=len(findings),
                    metrics=asdict(node.metrics),
                )
            )

    # Sort candidates by ROI descending, then by squeeze descending
    candidates.sort(key=lambda c: (c.roi, c.squeeze), reverse=True)

    total_nodes = len([n for n in snapshot.nodes if n.id not in {".", "external"}])
    total_degraded = len(degraded_node_ids)
    clean_nodes = max(0, total_nodes - total_degraded)
    total_lift = round(sum(c.lift for c in candidates), 2)
    total_squeeze = round(sum(c.squeeze for c in candidates), 2)
    avg_roi = round(sum(c.roi for c in candidates) / len(candidates), 2) if candidates else 0.0

    return RepoAssessment(
        repo_name=repo_name,
        repo_path=str(repo),
        source_commit=snapshot.source_commit,
        total_nodes=total_nodes,
        degraded_nodes=total_degraded,
        clean_nodes=clean_nodes,
        total_lift=total_lift,
        total_squeeze=total_squeeze,
        average_roi=avg_roi,
        antipattern_counts=dict(antipattern_counter),
        candidates=tuple(candidates),
    )


def walk_fleet(
    projects_root: Path,
    patterns: Sequence[str] = ("fleet-*", "tool-*"),
    days: int = 30,
    config_path: Path | None = None,
) -> FleetAssessment:
    """Walk all matching fleet and tool repos, assessing each and compiling a fleet ledger."""
    root = projects_root.resolve()
    repo_dirs: list[Path] = []
    for pattern in patterns:
        for entry in root.glob(pattern):
            if entry.is_dir() and (entry / "pyproject.toml").is_file():
                repo_dirs.append(entry)

    repo_dirs.sort(key=lambda p: p.name)
    repo_summaries: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    fleet_antipatterns: Counter[str] = Counter()

    for r_dir in repo_dirs:
        try:
            assessment = assess_repo(r_dir, days=days, config_path=config_path)
            for k, count in assessment.antipattern_counts.items():
                fleet_antipatterns[k] += count

            repo_summaries.append(
                {
                    "repo": assessment.repo_name,
                    "path": assessment.repo_path,
                    "total_nodes": assessment.total_nodes,
                    "degraded_nodes": assessment.degraded_nodes,
                    "clean_nodes": assessment.clean_nodes,
                    "total_lift": assessment.total_lift,
                    "total_squeeze": assessment.total_squeeze,
                    "average_roi": assessment.average_roi,
                    "top_candidates_count": len(assessment.candidates),
                    "antipatterns": assessment.antipattern_counts,
                }
            )

            for cand in assessment.candidates:
                cand_dict = cand.to_dict()
                cand_dict["repo"] = assessment.repo_name
                all_candidates.append(cand_dict)
        except Exception as exc:  # noqa: BLE001
            repo_summaries.append(
                {
                    "repo": r_dir.name,
                    "path": str(r_dir),
                    "error": str(exc),
                }
            )

    # Rank all fleet candidates globally by ROI
    all_candidates.sort(key=lambda c: (c["roi"], c["squeeze"]), reverse=True)

    return FleetAssessment(
        total_repos=len(repo_dirs),
        total_candidates=len(all_candidates),
        repo_summaries=repo_summaries,
        top_fleet_candidates=all_candidates[:50],  # top 50 across the fleet
        antipattern_distribution=dict(fleet_antipatterns),
    )


def write_assessment(payload: dict[str, Any], out_path: Path) -> None:
    """Atomically write an assessment JSON file."""
    # Ensure directory exists without using .parent (use dirname)
    dir_path = Path(os.path.dirname(out_path.resolve()))
    dir_path.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(out_path) + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, out_path)
