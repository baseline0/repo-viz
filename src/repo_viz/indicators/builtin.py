"""Built-in evaluators. Each is a pure function of a node and its context.

Threshold rule: a value at or above a threshold takes that state. For codes where
higher is better, a value at or below the low/high break-even takes the worse state.

## Specification Map

- ``security`` / ``boundary`` — qualitative tag-based evaluators.
- ``complexity`` / ``churn`` — quantitative threshold evaluators.
- ``hygiene`` / ``sentinel`` — typing and structural-smell evaluators.
- ``coverage`` — optional evaluator; returns ``na`` unless coverage data is supplied.
"""

from __future__ import annotations

from repo_viz.indicators.spec import Evaluation, EvaluationContext, State
from repo_viz.model import EdgeKind, Node

_COMPLEXITY_PARTIAL = 10
_COMPLEXITY_VIOLATION = 15
_CHURN_PARTIAL = 5
_CHURN_VIOLATION = 20
_DRIFT_PARTIAL = 5
_DRIFT_VIOLATION = 12
_FRICTION_PARTIAL = 8
_FRICTION_VIOLATION = 20
_COCHANGE_PARTIAL = 2
_COCHANGE_VIOLATION = 5
_COVERAGE_PARTIAL = 0.5
_COVERAGE_VERIFIED = 0.8
_SATD_PARTIAL = 1
_SATD_VIOLATION = 3
_HOTSPOT_PARTIAL = 20
_HOTSPOT_VIOLATION = 50
_COUPLING_PARTIAL = 10
_COUPLING_VIOLATION = 20
_CH_LOW = 4.9
_CH_HIGH = 7.1


def _threshold(context: EvaluationContext, name: str, default: float) -> float:
    """Thresholds are context-specific; config overrides the literature priors."""
    return context.thresholds.get(name, default)


def _node_path(node: Node, context: EvaluationContext) -> str:
    """Resolve a symbol to its enclosing file path so file-level producers apply."""
    current = node
    seen: set[str] = set()
    while current.path is None and current.parent is not None and current.parent not in seen:
        seen.add(current.parent)
        parent = next((item for item in context.graph.nodes if item.id == current.parent), None)
        if parent is None:
            break
        current = parent
    return current.path or node.id


def _produced(context: EvaluationContext, metric: str, node: Node) -> float | None:
    """Read a producer-supplied value for this file, falling back to the node id."""
    values = context.values.get(metric, {})
    found = values.get(_node_path(node, context))
    return found if found is not None else values.get(node.id)


def _churn_for(node: Node, context: EvaluationContext) -> int:
    """Churn lives on file nodes; symbol nodes inherit their enclosing file's count."""
    if node.metrics.churn_30d:
        return node.metrics.churn_30d
    path = _node_path(node, context)
    return next(
        (item.metrics.churn_30d for item in context.graph.nodes if item.path == path and item.metrics.churn_30d),
        0,
    )


def security(node: Node, _context: EvaluationContext) -> Evaluation:
    tags = node.tags
    egress = {tag for tag in tags if tag.startswith("egress:")}
    if "secret" in tags or "egress:exec" in tags:
        return Evaluation(State.VIOLATION, ",".join(sorted(egress | {"secret"})), "secret source or exec egress")
    if egress or "ingress" in tags:
        return Evaluation(State.PARTIAL, ",".join(sorted(egress)), "external interaction present")
    return Evaluation(State.NA, None, "no ingress or egress evidence")


def boundary(node: Node, _context: EvaluationContext) -> Evaluation:
    if "cycle" in node.tags:
        return Evaluation(State.VIOLATION, "cycle", "circular boundary crossing")
    if "private_import" in node.tags:
        return Evaluation(State.PARTIAL, "private_import", "private cross-boundary import")
    if "public_only" in node.tags:
        return Evaluation(State.VERIFIED, "public_only", "public interfaces only")
    return Evaluation(State.NA, None, "no boundary evidence")


def complexity(node: Node, context: EvaluationContext) -> Evaluation:
    value = node.metrics.complexity
    if value <= 0:
        return Evaluation(State.NA, 0, "no complexity evidence")
    partial = _threshold(context, "partial", _COMPLEXITY_PARTIAL)
    violation = _threshold(context, "violation", _COMPLEXITY_VIOLATION)
    if value >= violation:
        return Evaluation(State.VIOLATION, value, f"complexity {value} > {violation}")
    if value >= partial:
        return Evaluation(State.PARTIAL, value, f"complexity {value} > {partial}")
    return Evaluation(State.VERIFIED, value, "complexity within budget")


def hygiene(node: Node, _context: EvaluationContext) -> Evaluation:
    if "untyped" in node.tags:
        return Evaluation(State.PARTIAL, "untyped", "missing annotations")
    if "typed" in node.tags:
        return Evaluation(State.VERIFIED, "typed", "all arguments and return annotated")
    return Evaluation(State.NA, None, "no typing evidence")


def sentinel(node: Node, _context: EvaluationContext) -> Evaluation:
    if "god_class" in node.tags or "dead_code" in node.tags:
        return Evaluation(State.VIOLATION, "smell", "structural antipattern detected")
    if "global_state" in node.tags:
        return Evaluation(State.VIOLATION, "global_state", "coupling to mutable global/module-level state")
    if "uninjected_dependency" in node.tags:
        return Evaluation(State.VIOLATION, "uninjected_dependency", "tight coupling / lacks injectable dependencies")
    if "duplicate" in node.tags:
        return Evaluation(State.PARTIAL, "duplicate", "duplicate structure detected")
    if "tight_coupling" in node.tags:
        return Evaluation(State.PARTIAL, "tight_coupling", "tight coupling detected")
    if node.kind.value == "symbol":
        return Evaluation(State.VERIFIED, None, "no structural smell")
    return Evaluation(State.NA, None, "no structural evidence")


def coverage(node: Node, context: EvaluationContext) -> Evaluation:
    """Only meaningful when the caller supplies a coverage mapping."""
    ratio = context.coverage.get(node.path or "") or context.coverage.get(node.id)
    if ratio is None:
        return Evaluation(State.NA, None, "coverage not configured")
    if ratio >= _COVERAGE_VERIFIED:
        return Evaluation(State.VERIFIED, ratio, "coverage at or above 0.8")
    if ratio >= _COVERAGE_PARTIAL:
        return Evaluation(State.PARTIAL, ratio, "coverage between 0.5 and 0.8")
    return Evaluation(State.VIOLATION, ratio, "coverage below 0.5")


def churn(node: Node, context: EvaluationContext) -> Evaluation:
    if context.trigger == "change" and node.path not in context.changed_paths:
        return Evaluation(State.NA, None, "path not in this change set")
    value = node.metrics.churn_30d
    if value >= _threshold(context, "violation", _CHURN_VIOLATION):
        return Evaluation(State.VIOLATION, value, f"{value} touches in window")
    if value >= _threshold(context, "partial", _CHURN_PARTIAL):
        return Evaluation(State.PARTIAL, value, f"{value} touches in window")
    return Evaluation(State.VERIFIED, value, "low churn")


def coupling(node: Node, context: EvaluationContext) -> Evaluation:
    """Fan-in plus fan-out; structural design metrics dominate degradation studies."""
    produced = _produced(context, "coupling", node)
    value = produced if produced is not None else node.metrics.fan_in + node.metrics.fan_out
    if value <= 0:
        return Evaluation(State.NA, 0, "no coupling evidence")
    if value >= _threshold(context, "violation", _COUPLING_VIOLATION):
        return Evaluation(State.VIOLATION, value, "high coupling")
    if value >= _threshold(context, "partial", _COUPLING_PARTIAL):
        return Evaluation(State.PARTIAL, value, "elevated coupling")
    return Evaluation(State.VERIFIED, value, "coupling within budget")


def hotspot(node: Node, context: EvaluationContext) -> Evaluation:
    """Churn x coupling: the prioritisation signal used by industrial friction studies."""
    produced = _produced(context, "hotspot", node)
    value = (
        produced if produced is not None else _churn_for(node, context) * (node.metrics.fan_in + node.metrics.fan_out)
    )
    if value <= 0:
        return Evaluation(State.NA, 0, "no hotspot evidence")
    if value >= _threshold(context, "violation", _HOTSPOT_VIOLATION):
        return Evaluation(State.VIOLATION, value, "hotspot above budget")
    if value >= _threshold(context, "partial", _HOTSPOT_PARTIAL):
        return Evaluation(State.PARTIAL, value, "hotspot elevated")
    return Evaluation(State.VERIFIED, value, "low hotspot score")


def satd(node: Node, context: EvaluationContext) -> Evaluation:
    """Self-admitted technical debt; requires a TODO/FIXME producer, never inferred."""
    value = _produced(context, "satd", node)
    if value is None:
        return Evaluation(State.NA, None, "SATD producer not configured")
    if value >= _threshold(context, "violation", _SATD_VIOLATION):
        return Evaluation(State.VIOLATION, value, "multiple debt markers")
    if value >= _threshold(context, "partial", _SATD_PARTIAL):
        return Evaluation(State.PARTIAL, value, "debt marker present")
    return Evaluation(State.VERIFIED, value, "no debt markers")


def code_health(node: Node, context: EvaluationContext) -> Evaluation:
    """Composite health proxy; requires an external producer (not the proprietary CodeScore)."""
    value = _produced(context, "code_health", node)
    if value is None:
        return Evaluation(State.NA, None, "external health producer not configured")
    if value <= _threshold(context, "low", _CH_LOW):
        return Evaluation(State.VIOLATION, value, "below the low-health break-even")
    if value <= _threshold(context, "high", _CH_HIGH):
        return Evaluation(State.PARTIAL, value, "between low and high break-even")
    return Evaluation(State.VERIFIED, value, "above the high break-even")


def arch_drift(node: Node, context: EvaluationContext) -> Evaluation:
    """Cross-boundary macro edges touching a membrane and its descendants."""
    if node.kind.value != "membrane":
        return Evaluation(State.NA, None, "structural drift is a membrane-level signal")
    members = {node.id}
    growing = True
    while growing:
        growing = False
        for candidate in context.graph.nodes:
            if candidate.parent in members and candidate.id not in members:
                members.add(candidate.id)
                growing = True
    value = sum(
        1
        for edge in context.graph.edges
        if edge.kind is EdgeKind.AGGREGATE and (edge.source in members or edge.target in members)
    )
    if value <= 0:
        return Evaluation(State.NA, 0, "no cross-boundary evidence")
    if value >= _threshold(context, "violation", _DRIFT_VIOLATION):
        return Evaluation(State.VIOLATION, value, "many cross-boundary interactions")
    if value >= _threshold(context, "partial", _DRIFT_PARTIAL):
        return Evaluation(State.PARTIAL, value, "elevated cross-boundary interactions")
    return Evaluation(State.VERIFIED, value, "few cross-boundary interactions")


def cognitive_friction(node: Node, context: EvaluationContext) -> Evaluation:
    """Nesting-aware complexity multiplied by the enclosing file's churn."""
    value = node.metrics.cognitive_complexity * _churn_for(node, context)
    if value <= 0:
        return Evaluation(State.NA, 0, "no cognitive complexity evidence")
    if value >= _threshold(context, "violation", _FRICTION_VIOLATION):
        return Evaluation(State.VIOLATION, value, "high cognitive friction")
    if value >= _threshold(context, "partial", _FRICTION_PARTIAL):
        return Evaluation(State.PARTIAL, value, "elevated cognitive friction")
    return Evaluation(State.VERIFIED, value, "low cognitive friction")


def cochange(node: Node, context: EvaluationContext) -> Evaluation:
    """Observed co-edit frequency; requires a git-history producer."""
    value = _produced(context, "cochange", node)
    if value is None:
        return Evaluation(State.NA, None, "co-change producer not configured")
    if value >= _threshold(context, "violation", _COCHANGE_VIOLATION):
        return Evaluation(State.VIOLATION, value, "frequent co-change")
    if value >= _threshold(context, "partial", _COCHANGE_PARTIAL):
        return Evaluation(State.PARTIAL, value, "co-change observed")
    return Evaluation(State.VERIFIED, value, "little co-change")
