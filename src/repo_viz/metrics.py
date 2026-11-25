"""Pure static metrics used by the snapshot builder.

## Specification Map

- ``cyclomatic`` — branch count over an AST statement list.
- ``loc`` — physical lines occupied by an AST node.
- ``fan_counts`` — in/out degree per node from the leaf edge set.
"""

from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Iterable

from repo_viz.model import Edge, Node

_BRANCH_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.Assert)
_BOOL_BRANCHES = (ast.And, ast.Or)


def cyclomatic(statements: Iterable[ast.stmt]) -> int:
    """Count decision points in a function body, starting from one linear path."""
    score = 1
    for statement in statements:
        for node in ast.walk(statement):
            if isinstance(node, _BRANCH_NODES):
                score += 1
            elif isinstance(node, ast.BoolOp) and isinstance(node.op, _BOOL_BRANCHES):
                score += len(node.values) - 1
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                score += len(node.generators)
    return score


def loc(node: ast.AST) -> int:
    """Return the physical line span of an AST node."""
    start = getattr(node, "lineno", 0)
    end = getattr(node, "end_lineno", start)
    return max(0, end - start + 1)


def fan_counts(edges: Iterable[Edge]) -> dict[str, tuple[int, int]]:
    """Return ``node_id -> (fan_in, fan_out)`` over the given edges."""
    incoming: Counter[str] = Counter()
    outgoing: Counter[str] = Counter()
    for edge in edges:
        outgoing[edge.source] += edge.weight
        incoming[edge.target] += edge.weight
    return {node_id: (incoming[node_id], outgoing[node_id]) for node_id in incoming.keys() | outgoing.keys()}


def is_untyped(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True when the function has any unannotated argument or no return annotation."""
    args = [*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs]
    if function.args.vararg is not None:
        args.append(function.args.vararg)
    if function.args.kwarg is not None:
        args.append(function.args.kwarg)
    return any(argument.annotation is None for argument in args) or function.returns is None


def with_fan(nodes: tuple[Node, ...], edges: Iterable[Edge]) -> tuple[Node, ...]:
    """Return nodes with fan-in and fan-out copied from their metrics."""
    counts = fan_counts(edges)
    result: list[Node] = []
    for node in nodes:
        fan_in, fan_out = counts.get(node.id, (0, 0))
        metrics = node.metrics
        result.append(
            Node(
                id=node.id,
                label=node.label,
                kind=node.kind,
                parent=node.parent,
                lod_rank=node.lod_rank,
                path=node.path,
                tags=node.tags,
                metrics=type(metrics)(
                    complexity=metrics.complexity,
                    loc=metrics.loc,
                    fan_in=fan_in,
                    fan_out=fan_out,
                    churn_30d=metrics.churn_30d,
                    coverage=metrics.coverage,
                ),
                status=node.status,
            )
        )
    return tuple(result)
