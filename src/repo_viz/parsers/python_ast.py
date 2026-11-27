"""Standard-library AST parser: imports, calls, inheritance, receptors and sinks.

## Specification Map

- ``parse_source`` — pure entry point; takes source text, never touches the filesystem.
- ``ParseResult`` — symbol nodes plus leaf edges for one module.
- ``resolve_from`` — Python relative-import resolution against the containing package.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass

from repo_viz.classify import classify_call, is_ingress_decorator
from repo_viz.metrics import cognitive_complexity, cyclomatic, is_untyped, loc
from repo_viz.model import Edge, EdgeKind, Metrics, Node, NodeKind, Track

EXTERNAL_ID = "external"
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_GOD_CLASS_METHODS = 30

_EXCLUDED_INSTANTIATIONS = frozenset(
    {
        "BaseException",
        "Exception",
        "ValueError",
        "TypeError",
        "KeyError",
        "IndexError",
        "AttributeError",
        "RuntimeError",
        "NotImplementedError",
        "IOError",
        "OSError",
        "FileNotFoundError",
        "StopIteration",
        "PermissionError",
        "TimeoutError",
        "Path",
        "PurePath",
        "PosixPath",
        "WindowsPath",
        "UUID",
        "Decimal",
        "datetime",
        "date",
        "time",
        "timedelta",
        "timezone",
        "UTC",
        "Counter",
        "defaultdict",
        "deque",
        "OrderedDict",
        "BytesIO",
        "StringIO",
        "Pattern",
        "Match",
    }
)


def is_likely_class_instantiation(expr: ast.expr) -> bool:
    """Return True if an AST call target represents a class instantiation candidate for DI."""
    name: str | None = None
    if isinstance(expr, ast.Name):
        name = expr.id
    elif isinstance(expr, ast.Attribute):
        name = expr.attr
    if name is not None:
        if name in _EXCLUDED_INSTANTIATIONS:
            return False
        # PascalCase / CamelCase: starts with uppercase, has lowercase, no underscore
        if len(name) > 1 and name[0].isupper() and not name.isupper() and "_" not in name:
            return True
    return False


def has_global_state_access(node: ast.AST) -> bool:
    """Return True if AST node uses global or nonlocal statements."""
    return any(isinstance(child, (ast.Global, ast.Nonlocal)) for child in ast.walk(node))


def has_singleton_access(node: ast.AST) -> bool:
    """Return True if AST node calls singleton accessors or global service locators."""
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in ("get_instance", "instance", "get_default", "default_instance")
        ):
            return True
    return False


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Symbol nodes and leaf edges extracted from one module."""

    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]


def resolve_from(module: str | None, level: int, package_parts: tuple[str, ...]) -> str:
    """Resolve a ``from ... import`` target to a dotted module name."""
    if level == 0:
        return module or ""
    keep = max(0, len(package_parts) - (level - 1))
    parts = list(package_parts[:keep])
    if module:
        parts.extend(module.split("."))
    return ".".join(parts)


def dotted_name(expr: ast.expr) -> str | None:
    """Return the dotted spelling of a Name/Attribute chain, or None."""
    parts: list[str] = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if isinstance(expr, ast.Name):
        parts.append(expr.id)
        return ".".join(reversed(parts))
    return None


class _Collector(ast.NodeVisitor):
    def __init__(
        self,
        module_id: str,
        package_parts: tuple[str, ...],
        known_modules: Mapping[str, str],
    ) -> None:
        self.module_id = module_id
        self.package_parts = package_parts
        self.known_modules = known_modules
        self.nodes: list[Node] = []
        self.edges: list[Edge] = []
        self.aliases: dict[str, str] = {}
        self.defined: dict[str, str] = {}
        self.symbol_ids: set[str] = set()
        self.node_ids: dict[int, str] = {}
        self.scopes: list[str] = []

    @property
    def scope(self) -> str:
        return self.scopes[-1] if self.scopes else self.module_id

    def _add_symbol(
        self,
        symbol_id: str,
        node: ast.AST,
        parent: str,
        lod_rank: int,
        tags: frozenset[str],
        complexity: int = 0,
        cognitive: int = 0,
    ) -> str:
        if symbol_id in self.symbol_ids:
            symbol_id = f"{symbol_id}@{getattr(node, 'lineno', 0)}"
        self.node_ids[id(node)] = symbol_id
        self.symbol_ids.add(symbol_id)
        self.nodes.append(
            Node(
                id=symbol_id,
                label=getattr(node, "name", symbol_id),
                kind=NodeKind.SYMBOL,
                parent=parent,
                lod_rank=lod_rank,
                path=None,
                tags=tags,
                metrics=Metrics(complexity=complexity, cognitive_complexity=cognitive, loc=loc(node)),
            )
        )
        return symbol_id

    def _function_tags(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
        tags: set[str] = set()
        decorators = [
            dotted_name(decorator.func if isinstance(decorator, ast.Call) else decorator)
            for decorator in node.decorator_list
        ]
        if any(name is not None and is_ingress_decorator(name) for name in decorators):
            tags.add("ingress")
        tags.add("untyped" if is_untyped(node) else "typed")
        if has_global_state_access(node):
            tags.add("global_state")
            tags.add("tight_coupling")
        if has_singleton_access(node):
            tags.add("tight_coupling")
        return frozenset(tags)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        class_id = f"{self.module_id}::{node.name}"
        method_count = sum(isinstance(item, _FUNCTIONS) for item in node.body)

        init_method = next(
            (item for item in node.body if isinstance(item, _FUNCTIONS) and item.name == "__init__"),
            None,
        )
        injectable_params: list[str] = []
        if init_method is not None:
            injectable_params = [arg.arg for arg in init_method.args.args if arg.arg != "self"] + [
                arg.arg for arg in init_method.args.kwonlyargs
            ]
            if init_method.args.vararg:
                injectable_params.append(init_method.args.vararg.arg)
            if init_method.args.kwarg:
                injectable_params.append(init_method.args.kwarg.arg)
        has_injectable_init = len(injectable_params) > 0

        concrete_instantiations = 0
        uses_global = False
        uses_singleton = False
        for item in node.body:
            if isinstance(item, _FUNCTIONS):
                for child in ast.walk(item):
                    if isinstance(child, ast.Call) and is_likely_class_instantiation(child.func):
                        concrete_instantiations += 1
                if has_global_state_access(item):
                    uses_global = True
                if has_singleton_access(item):
                    uses_singleton = True

        tags: set[str] = set()
        if method_count > _GOD_CLASS_METHODS:
            tags.add("god_class")
        if uses_global:
            tags.add("global_state")
            tags.add("tight_coupling")
        if uses_singleton:
            tags.add("tight_coupling")
        if concrete_instantiations > 0 and not has_injectable_init:
            tags.add("uninjected_dependency")
            tags.add("tight_coupling")
        if (
            (method_count >= 10 or loc(node) >= 100)
            and not has_injectable_init
            and (concrete_instantiations > 0 or uses_global)
        ):
            tags.add("god_component")
            tags.add("uninjected_dependency")

        class_id = self._add_symbol(
            class_id,
            node,
            self.scope,
            3,
            frozenset(tags),
            cyclomatic(node.body),
            cognitive_complexity(node.body),
        )
        self.defined[node.name] = class_id
        for item in node.body:
            if isinstance(item, _FUNCTIONS):
                method_id = f"{class_id}::{item.name}"
                method_id = self._add_symbol(
                    method_id,
                    item,
                    class_id,
                    4,
                    self._function_tags(item),
                    cyclomatic(item.body),
                    cognitive_complexity(item.body),
                )
                self.defined[f"{node.name}.{item.name}"] = method_id
        self.scopes.append(class_id)
        self.generic_visit(node)
        self.scopes.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        existing = self.node_ids.get(id(node))
        if existing is None:
            symbol_id = f"{self.scope}::{node.name}"
            symbol_id = self._add_symbol(
                symbol_id,
                node,
                self.scope,
                4,
                self._function_tags(node),
                cyclomatic(node.body),
                cognitive_complexity(node.body),
            )
            self.defined.setdefault(node.name, symbol_id)
        else:
            symbol_id = existing
        self.scopes.append(symbol_id)
        self.generic_visit(node)
        self.scopes.pop()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.aliases[alias.asname or alias.name.split(".")[0]] = alias.name
            self._import_edge(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = resolve_from(node.module, node.level, self.package_parts)
        for alias in node.names:
            self.aliases[alias.asname or alias.name] = module
            self._import_edge(module, node.lineno)
        self.generic_visit(node)

    def _import_edge(self, dotted: str, line: int) -> None:
        target = self.known_modules.get(dotted)
        if target is not None and target != self.module_id:
            self.edges.append(
                Edge(
                    source=self.module_id,
                    target=target,
                    kind=EdgeKind.IMPORT,
                    tracks=frozenset({Track.CONTROL}),
                    line=line,
                )
            )

    def visit_Call(self, node: ast.Call) -> None:
        dotted = self._resolve_call(node.func)
        if dotted is not None:
            kind, tracks, tags = classify_call(dotted)
            if tags:
                self._attach_tags(tags)
                target = self.known_modules.get(dotted, EXTERNAL_ID)
            elif dotted in self.symbol_ids:
                target, kind, tracks = dotted, EdgeKind.CALL, frozenset({Track.CONTROL})
            else:
                module = self._longest_known_prefix(dotted)
                if module is None or module == self.module_id:
                    return
                target, kind, tracks = module, EdgeKind.CALL, frozenset({Track.CONTROL})
            if target != self.scope:  # recursion is a self-loop, not an interaction
                self.edges.append(
                    Edge(
                        source=self.scope,
                        target=target,
                        kind=kind,
                        tracks=tracks,
                        line=node.lineno,
                    )
                )
        self.generic_visit(node)

    def _attach_tags(self, tags: frozenset[str]) -> None:
        scope_id = self.scope
        updated = []
        for node in self.nodes:
            if node.id == scope_id:
                updated.append(
                    Node(
                        id=node.id,
                        label=node.label,
                        kind=node.kind,
                        parent=node.parent,
                        lod_rank=node.lod_rank,
                        path=node.path,
                        tags=node.tags | tags,
                        metrics=node.metrics,
                        status=node.status,
                    )
                )
            else:
                updated.append(node)
        self.nodes = updated

    def _longest_known_prefix(self, dotted: str) -> str | None:
        candidates = [module for module in self.known_modules if dotted.startswith(module)]
        if not candidates:
            return None
        module = max(candidates, key=len)
        return self.known_modules[module]

    def _resolve_call(self, func: ast.expr) -> str | None:
        if isinstance(func, ast.Name):
            if func.id in self.defined:
                return self.defined[func.id]
            return self.aliases.get(func.id)
        if isinstance(func, ast.Attribute):
            parts: list[str] = []
            current: ast.expr = func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                base = current.id
                if base in self.aliases:
                    return ".".join([self.aliases[base], *reversed(parts)])
                if base in self.defined:
                    candidate = f"{self.defined[base]}::{'.'.join(reversed(parts))}"
                    return candidate if candidate in self.symbol_ids else None
        return None


def parse_source(
    source: str,
    *,
    module_id: str,
    package_parts: tuple[str, ...] = (),
    known_modules: Mapping[str, str] | None = None,
) -> ParseResult:
    """Parse one module's source text into symbol nodes and leaf edges."""
    tree = ast.parse(source)
    collector = _Collector(module_id, package_parts, dict(known_modules or {}))
    collector.visit(tree)
    # Inheritance edges: resolved after all classes are known.
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        class_id = collector.node_ids.get(id(node))
        if class_id is None:
            continue
        for base in node.bases:
            dotted = dotted_name(base) or ""
            target = collector.defined.get(dotted)
            if target is None:
                alias = collector.aliases.get(dotted)
                target = collector._longest_known_prefix(alias) if alias is not None else None
            if target is None:
                target = collector._longest_known_prefix(dotted)
            if (
                target is not None
                and target != class_id
                and (target in collector.symbol_ids or target in collector.known_modules.values())
            ):
                collector.edges.append(
                    Edge(
                        source=class_id,
                        target=target,
                        kind=EdgeKind.INHERIT,
                        tracks=frozenset({Track.CONTROL}),
                        line=node.lineno,
                    )
                )
    return ParseResult(nodes=tuple(collector.nodes), edges=tuple(collector.edges))
