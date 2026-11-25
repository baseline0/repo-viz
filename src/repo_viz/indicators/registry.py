"""Resolve and run configured indicator evaluators.

## Specification Map

- ``resolve`` — dotted ``module:function`` lookup through importlib.
- ``evaluate`` — run every enabled, trigger-matching indicator over every node.
- ``write_results`` — atomic write of the derived indicator artifact.
"""

from __future__ import annotations

import importlib
import json
import os
import signal
import threading
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from repo_viz.indicators.spec import (
    Evaluation,
    EvaluationContext,
    Indicator,
    IndicatorConfig,
    IndicatorResult,
    State,
)
from repo_viz.model import Node

Evaluator = Callable[[Node, EvaluationContext], Evaluation]


def resolve(compute: str) -> Evaluator:
    """Import the evaluator named by ``module:function``."""
    module_name, function_name = compute.split(":", 1)
    evaluator = getattr(importlib.import_module(module_name), function_name)
    if not callable(evaluator):
        raise TypeError(f"{compute} is not callable")
    return cast(Evaluator, evaluator)


def _evaluate_one(evaluator: Evaluator, node: Node, context: EvaluationContext, timeout: int) -> Evaluation:
    """Evaluate one node, enforcing the configured budget on the main thread."""
    if timeout <= 0 or threading.current_thread() is not threading.main_thread():
        return evaluator(node, context)

    def on_alarm(_signum: int, _frame: object) -> None:
        raise TimeoutError("indicator exceeded its time budget")

    previous = signal.signal(signal.SIGALRM, on_alarm)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, timeout)
    try:
        return evaluator(node, context)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)


def evaluate(config: IndicatorConfig, context: EvaluationContext) -> tuple[IndicatorResult, ...]:
    """Return one result per enabled indicator per node for this trigger."""
    now = datetime.now(UTC).isoformat()
    results: list[IndicatorResult] = []
    for indicator in config.enabled_for(context.trigger):
        evaluator = resolve(indicator.compute)
        scoped = replace(context, thresholds=indicator.thresholds) if indicator.thresholds else context
        for node in context.graph.nodes:
            try:
                evaluation = _evaluate_one(evaluator, node, scoped, indicator.timeout_seconds)
            except Exception as cause:  # a broken indicator must not break the view
                evaluation = Evaluation(State.NA, None, f"{type(cause).__name__}: {cause}")
            results.append(
                IndicatorResult(
                    indicator_id=indicator.id,
                    node_id=node.id,
                    trigger=context.trigger,
                    state=evaluation.state,
                    value=evaluation.value,
                    evidence=evaluation.evidence,
                    computed_at=now,
                )
            )
    return tuple(results)


def results_to_dict(results: tuple[IndicatorResult, ...]) -> dict[str, Any]:
    """Return a JSON-ready indicator artifact."""
    items: list[dict[str, Any]] = []
    for result in results:
        item = asdict(result)
        item["state"] = result.state.value
        items.append(item)
    return {"version": 1, "results": items}


def write_results(results: tuple[IndicatorResult, ...], out_path: Path) -> None:
    """Atomically write the derived indicator artifact."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_name(f".{out_path.name}.tmp")
    temporary.write_text(
        json.dumps(results_to_dict(results), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, out_path)


def by_node(results: tuple[IndicatorResult, ...]) -> dict[str, tuple[IndicatorResult, ...]]:
    """Group results by node id for the viewer."""
    grouped: dict[str, list[IndicatorResult]] = {}
    for result in results:
        grouped.setdefault(result.node_id, []).append(result)
    return {node_id: tuple(items) for node_id, items in grouped.items()}


__all__ = ["Indicator", "Evaluator", "resolve", "evaluate", "write_results", "by_node"]
