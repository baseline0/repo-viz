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
from itertools import chain

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


class _CognitiveVisitor(ast.NodeVisitor):
    """Nesting-aware complexity: each decision adds one plus its nesting depth."""

    def __init__(self) -> None:
        self.score = 0
        self.nesting = 0

    def _block(self, statements: Iterable[ast.stmt]) -> None:
        self.nesting += 1
        for statement in statements:
            self.visit(statement)
        self.nesting -= 1

    def _decision(self, node: ast.AST, *blocks: Iterable[ast.stmt]) -> None:
        self.score += 1 + self.nesting
        for child in ast.iter_child_nodes(node):
            if not isinstance(child, ast.stmt):
                self.visit(child)
        for block in blocks:
            self._block(block)

    def visit_If(self, node: ast.If) -> None:
        self._decision(node, node.body, node.orelse)

    def visit_For(self, node: ast.For) -> None:
        self._decision(node, node.body, node.orelse)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._decision(node, node.body, node.orelse)

    def visit_While(self, node: ast.While) -> None:
        self._decision(node, node.body, node.orelse)

    def visit_Try(self, node: ast.Try) -> None:
        self._decision(
            node,
            chain(node.body, *(handler.body for handler in node.handlers), node.orelse, node.finalbody),
        )

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._decision(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.score += len(node.values) - 1
        self.generic_visit(node)


def cognitive_complexity(node: ast.AST | Iterable[ast.stmt]) -> int:
    """Return nesting-aware cognitive complexity for an AST node or statement list."""
    visitor = _CognitiveVisitor()
    if isinstance(node, ast.AST):
        visitor.visit(node)
    else:
        for statement in node:
            visitor.visit(statement)
    return visitor.score


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
                    cognitive_complexity=metrics.cognitive_complexity,
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
