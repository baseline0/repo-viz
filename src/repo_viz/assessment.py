"""Antipattern detection, calibrated Cost/Blast/Squeeze calculation, and repository assessment.

## Specification Map

- ``compute_change_cost`` — estimate physical authoring effort and complexity.
- ``compute_blast_radius`` — estimate downstream breakage risk and API exposure.
- ``compute_lift`` — combined effort index (change_cost + blast_radius).
- ``compute_squeeze_breakdown`` — separate structural debt from capped hygiene noise.
- ``compute_roi`` — calculate ROI = squeeze / (change_cost + blast_radius) * 10.
- ``assign_tier`` — classify candidates into Tier A/B/C/D actionability buckets.
- ``detect_antipatterns`` — classify architectural and code-health smells.
- ``assess_repo`` — assess a repository and rank refactoring proposals by ROI and Tier.
- ``walk_fleet`` — assess all matching fleet and tool repositories.
"""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
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

ASSESSMENT_SCHEMA = "repo-viz/assessment@2"
FLEET_ASSESSMENT_SCHEMA = "repo-viz/fleet-assessment@2"
DEFAULT_INDICATOR_CONFIG = CONFIG_DIR / "indicators.toml"


class Antipattern:
    GOD_COMPONENT = "god_component"
    COGNITIVE_HOTSPOT = "cognitive_hotspot"
    COUPLING_HUB = "coupling_hub"
    BOUNDARY_LEAK = "boundary_leak"
    HYGIENE_ROT = "hygiene_rot"
    SATD_DEBT = "satd_debt"
    SECURITY_SMELL = "security_smell"
    TIGHT_COUPLING = "tight_coupling"
    GLOBAL_STATE = "global_state"
    UNINJECTED_DEPENDENCY = "uninjected_dependency"


class RefactorTier(StrEnum):
    TIER_A = "tier_a"  # High Squeeze, Contained Blast Radius -> Prime Agent Target
    TIER_B = "tier_b"  # High Squeeze, High Blast Radius -> Needs Architectural ADR / Human Review
    TIER_C = "tier_c"  # Hygiene / Style Backlog -> Pre-commit Ratchet / Linter candidate
    TIER_D = "tier_d"  # High Cost, Low Squeeze -> Defer (Deficit Trap)


def compute_change_cost(metrics: Metrics) -> float:
    """Estimate physical authoring effort and cognitive complexity.

    - Physical size: LOC scaled by ~1.0 unit per 50 lines.
    - Authoring friction: Cognitive complexity and cyclomatic branch points.
    - Volatility factor: Recent churn multiplier (active code has higher test/verify friction).
    """
    loc_factor = max(0.5, metrics.loc / 50.0)
    complexity_factor = (metrics.cognitive_complexity / 10.0) + (metrics.complexity / 15.0)
    churn_factor = 1.0 + (0.05 * min(metrics.churn_30d, 10))
    cost = (loc_factor + complexity_factor) * churn_factor
    return round(max(1.0, cost), 2)


def compute_blast_radius(node: Node, metrics: Metrics) -> float:
    """Estimate downstream breakage risk, caller dependency scope, and API exposure.

    - Inbound callers: fan_in heavily weighted (each caller represents breakage risk).
    - Outbound entanglements: fan_out lightly weighted.
    - Membrane / Container level: higher hierarchy rank = wider blast radius.
    - Public / Ingress exposure: framework receptors (.route, .get, etc.) carry higher risk.
    """
    caller_risk = 1.0 + (0.35 * metrics.fan_in)
    outbound_risk = 0.05 * metrics.fan_out

    kind_multiplier = 1.0
    if node.kind is NodeKind.MEMBRANE:
        kind_multiplier = 2.0
    elif node.kind is NodeKind.FILE:
        kind_multiplier = 1.4

    exposure_bonus = 1.0 if "ingress" in node.tags else 0.0

    radius = (caller_risk + outbound_risk + exposure_bonus) * kind_multiplier
    return round(max(1.0, radius), 2)


def compute_lift(metrics: Metrics) -> float:
    """Combined effort index for backward compatibility: change_cost + blast_radius."""
    # Approximate blast radius without node reference for pure metrics compatibility
    loc_factor = max(0.5, metrics.loc / 50.0)
    complexity_factor = (metrics.cognitive_complexity / 10.0) + (metrics.complexity / 15.0)
    churn_factor = 1.0 + (0.05 * min(metrics.churn_30d, 10))
    cost = max(1.0, (loc_factor + complexity_factor) * churn_factor)

    caller_risk = 1.0 + (0.35 * metrics.fan_in) + (0.05 * metrics.fan_out)
    return round(cost + caller_risk, 2)


def compute_squeeze_breakdown(
    findings: Sequence[AuditFinding],
    metrics: Metrics,
) -> tuple[float, float, float]:
    """Calculate structural squeeze vs hygiene squeeze.

    Returns:
        (total_squeeze, structural_squeeze, hygiene_squeeze)
    """
    structural = 0.0
    hygiene_findings = 0

    for finding in findings:
        if finding.indicator_id == "hygiene":
            hygiene_findings += 1
        elif finding.indicator_id in ("boundary", "arch_drift"):
            structural += 20.0 if finding.severity == "high" else 8.0
        elif finding.indicator_id == "sentinel":
            structural += 15.0
        elif finding.indicator_id == "coupling":
            structural += 10.0
        elif finding.indicator_id == "satd":
            structural += 5.0
        elif finding.indicator_id == "security":
            structural += 10.0 if finding.severity == "high" else 4.0
        else:
            structural += 10.0 if finding.severity == "high" else 4.0

    # Cap hygiene points so typing noise cannot swamp architectural debt (max 4.0 pts)
    hygiene = min(hygiene_findings, 2) * 2.0

    # Cognitive load dividend
    if metrics.cognitive_complexity > 5:
        structural += (metrics.cognitive_complexity - 5) * 0.8

    # Friction dividend
    friction = metrics.cognitive_complexity * metrics.churn_30d
    if friction >= 20:
        structural += 10.0
    elif friction >= 8:
        structural += 4.0

    total = round(max(0.0, structural + hygiene), 2)
    return total, round(structural, 2), round(hygiene, 2)


def compute_squeeze(findings: Sequence[AuditFinding], metrics: Metrics) -> float:
    """Return total squeeze score."""
    total, _, _ = compute_squeeze_breakdown(findings, metrics)
    return total


def compute_roi(squeeze: float, change_cost: float, blast_radius: float) -> float:
    """Calculate the refactoring return on investment: squeeze / (cost + radius) * 10."""
    total_effort = change_cost + blast_radius
    if total_effort <= 0.0:
        return 0.0
    return round((squeeze / total_effort) * 10.0, 2)


def assign_tier(
    squeeze: float,
    structural_squeeze: float,
    change_cost: float,
    blast_radius: float,
    roi: float,
    antipatterns: Sequence[str],
) -> RefactorTier:
    """Assign candidate to an actionable decision tier."""
    # If findings are strictly hygiene/satd with minimal structural payoff -> Tier C
    if structural_squeeze <= 5.0 and set(antipatterns).issubset({Antipattern.HYGIENE_ROT, Antipattern.SATD_DEBT}):
        return RefactorTier.TIER_C

    # High payoff with manageable blast radius -> Tier A (Prime agent target)
    if structural_squeeze >= 18.0 and blast_radius <= 4.0 and change_cost <= 6.0 and roi >= 20.0:
        return RefactorTier.TIER_A

    # High payoff with wide blast radius -> Tier B (Architectural ADR required)
    if structural_squeeze >= 18.0 and blast_radius > 4.0:
        return RefactorTier.TIER_B

    # Moderate ROI with contained blast radius -> Tier A if structural payoff is solid
    if structural_squeeze >= 12.0 and blast_radius <= 3.0 and roi >= 15.0:
        return RefactorTier.TIER_A

    # Low payoff or poor ROI -> Tier D (Defer)
    return RefactorTier.TIER_D


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

    # Smells detected via findings and AST tags
    finding_indicators = {f.indicator_id for f in findings}
    if "boundary" in finding_indicators or "arch_drift" in finding_indicators:
        patterns.append(Antipattern.BOUNDARY_LEAK)
    if "hygiene" in finding_indicators:
        patterns.append(Antipattern.HYGIENE_ROT)
    if "satd" in finding_indicators:
        patterns.append(Antipattern.SATD_DEBT)
    if "security" in finding_indicators:
        patterns.append(Antipattern.SECURITY_SMELL)
    if "global_state" in node.tags:
        patterns.append(Antipattern.GLOBAL_STATE)
    if "uninjected_dependency" in node.tags:
        patterns.append(Antipattern.UNINJECTED_DEPENDENCY)
    if "tight_coupling" in node.tags:
        patterns.append(Antipattern.TIGHT_COUPLING)

    return tuple(sorted(dict.fromkeys(patterns)))


@dataclass(frozen=True, slots=True)
class RefactoringCandidate:
    """A prioritized refactoring candidate with decoupled cost, blast radius, and tiering."""

    node_id: str
    node_label: str
    path: str | None
    kind: str
    change_cost: float
    blast_radius: float
    lift: float
    squeeze: float
    structural_squeeze: float
    hygiene_squeeze: float
    roi: float
    tier: RefactorTier
    antipatterns: tuple[str, ...]
    suggested_actions: tuple[str, ...]
    findings_count: int
    metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["tier"] = self.tier.value if isinstance(self.tier, RefactorTier) else str(self.tier)
        return payload


@dataclass(frozen=True, slots=True)
class RepoAssessment:
    """Repository-wide assessment summary with ranked refactoring proposals."""

    repo_name: str
    repo_path: str
    source_commit: str
    total_nodes: int
    degraded_nodes: int
    clean_nodes: int
    total_change_cost: float
    total_blast_radius: float
    total_squeeze: float
    average_roi: float
    tier_counts: dict[str, int]
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
    tier_distribution: dict[str, int]
    antipattern_distribution: dict[str, int]
    repo_summaries: list[dict[str, Any]]
    top_tier_a_candidates: list[dict[str, Any]]
    top_tier_b_candidates: list[dict[str, Any]]
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
    """Run full static analysis on a repository and rank refactoring proposals by ROI and Tier."""
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
    tier_counter: Counter[str] = Counter()
    degraded_node_ids: set[str] = set()

    # Analyze all concrete file and symbol nodes (skip root container '.' and external)
    for node in snapshot.nodes:
        if node.id in {".", "external"}:
            continue
        if node.kind is NodeKind.MEMBRANE and not node.path:
            continue

        report: AuditReport = audit_component(snapshot, results, node.id)
        findings = report.findings
        change_cost = compute_change_cost(node.metrics)
        blast_radius = compute_blast_radius(node, node.metrics)
        lift = round(change_cost + blast_radius, 2)
        squeeze, struct_sq, hyg_sq = compute_squeeze_breakdown(findings, node.metrics)
        roi = compute_roi(squeeze, change_cost, blast_radius)
        antipatterns = detect_antipatterns(node, findings)
        tier = assign_tier(squeeze, struct_sq, change_cost, blast_radius, roi, antipatterns)

        if findings or antipatterns or squeeze > 0:
            degraded_node_ids.add(node.id)
            tier_counter[tier.value] += 1
            for ap in antipatterns:
                antipattern_counter[ap] += 1

            candidates.append(
                RefactoringCandidate(
                    node_id=node.id,
                    node_label=node.label,
                    path=node.path,
                    kind=node.kind.value,
                    change_cost=change_cost,
                    blast_radius=blast_radius,
                    lift=lift,
                    squeeze=squeeze,
                    structural_squeeze=struct_sq,
                    hygiene_squeeze=hyg_sq,
                    roi=roi,
                    tier=tier,
                    antipatterns=antipatterns,
                    suggested_actions=report.suggested_actions,
                    findings_count=len(findings),
                    metrics=asdict(node.metrics),
                )
            )

    # Sort candidates by Tier priority (Tier A first, then Tier B, then Tier D, then Tier C), then by ROI descending
    tier_order = {RefactorTier.TIER_A: 0, RefactorTier.TIER_B: 1, RefactorTier.TIER_D: 2, RefactorTier.TIER_C: 3}
    candidates.sort(key=lambda c: (tier_order.get(c.tier, 4), -c.roi, -c.structural_squeeze))

    total_nodes = len([n for n in snapshot.nodes if n.id not in {".", "external"}])
    total_degraded = len(degraded_node_ids)
    clean_nodes = max(0, total_nodes - total_degraded)
    total_cost = round(sum(c.change_cost for c in candidates), 2)
    total_radius = round(sum(c.blast_radius for c in candidates), 2)
    total_squeeze = round(sum(c.squeeze for c in candidates), 2)
    avg_roi = round(sum(c.roi for c in candidates) / len(candidates), 2) if candidates else 0.0

    return RepoAssessment(
        repo_name=repo_name,
        repo_path=str(repo),
        source_commit=snapshot.source_commit,
        total_nodes=total_nodes,
        degraded_nodes=total_degraded,
        clean_nodes=clean_nodes,
        total_change_cost=total_cost,
        total_blast_radius=total_radius,
        total_squeeze=total_squeeze,
        average_roi=avg_roi,
        tier_counts=dict(tier_counter),
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
    fleet_tiers: Counter[str] = Counter()

    for r_dir in repo_dirs:
        try:
            assessment = assess_repo(r_dir, days=days, config_path=config_path)
            for k, count in assessment.antipattern_counts.items():
                fleet_antipatterns[k] += count
            for t_val, count in assessment.tier_counts.items():
                fleet_tiers[t_val] += count

            repo_summaries.append(
                {
                    "repo": assessment.repo_name,
                    "path": assessment.repo_path,
                    "total_nodes": assessment.total_nodes,
                    "degraded_nodes": assessment.degraded_nodes,
                    "clean_nodes": assessment.clean_nodes,
                    "total_change_cost": assessment.total_change_cost,
                    "total_blast_radius": assessment.total_blast_radius,
                    "total_squeeze": assessment.total_squeeze,
                    "average_roi": assessment.average_roi,
                    "tier_counts": assessment.tier_counts,
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

    tier_a = [c for c in all_candidates if c["tier"] == RefactorTier.TIER_A.value]
    tier_b = [c for c in all_candidates if c["tier"] == RefactorTier.TIER_B.value]

    tier_a.sort(key=lambda c: (-c["roi"], -c["structural_squeeze"]))
    tier_b.sort(key=lambda c: (-c["roi"], -c["structural_squeeze"]))

    return FleetAssessment(
        total_repos=len(repo_dirs),
        total_candidates=len(all_candidates),
        tier_distribution=dict(fleet_tiers),
        antipattern_distribution=dict(fleet_antipatterns),
        repo_summaries=repo_summaries,
        top_tier_a_candidates=tier_a[:50],  # top 50 Tier A across the fleet
        top_tier_b_candidates=tier_b[:50],  # top 50 Tier B across the fleet
    )


def write_assessment(payload: dict[str, Any], out_path: Path) -> None:
    """Atomically write an assessment JSON file."""
    dir_path = Path(os.path.dirname(out_path.resolve()))
    dir_path.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(out_path) + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_path, out_path)


def write_csv_ledger(candidates: Sequence[dict[str, Any]], out_path: Path) -> None:
    """Write flat CSV ledger for spreadsheet review and human auditing."""
    dir_path = Path(os.path.dirname(out_path.resolve()))
    dir_path.mkdir(parents=True, exist_ok=True)
    tmp_path = Path(str(out_path) + ".tmp")
    fieldnames = [
        "repo",
        "node_id",
        "node_label",
        "path",
        "kind",
        "tier",
        "roi",
        "change_cost",
        "blast_radius",
        "squeeze",
        "structural_squeeze",
        "hygiene_squeeze",
        "findings_count",
        "antipatterns",
    ]
    with tmp_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for c in candidates:
            row = dict(c)
            row["antipatterns"] = ";".join(c.get("antipatterns", []))
            writer.writerow(row)
    os.replace(tmp_path, out_path)
