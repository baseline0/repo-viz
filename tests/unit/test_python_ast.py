"""The stdlib parser extracts hierarchy, imports, inheritance, receptors and sinks."""

from __future__ import annotations

from repo_viz.model import EdgeKind, NodeKind
from repo_viz.parsers.python_ast import EXTERNAL_ID, parse_source, resolve_from


def test_relative_import_resolution() -> None:
    assert resolve_from("core", 1, ("src", "pkg")) == "src.pkg.core"
    assert resolve_from("core", 2, ("src", "pkg")) == "src.core"
    assert resolve_from(None, 1, ("src", "pkg")) == "src.pkg"


def test_parser_extracts_symbols_imports_inheritance_and_sinks() -> None:
    source = """\
import httpx
from .core import Engine

class Child(Engine):
    def run(self):
        return httpx.get("https://example.test")
"""
    parsed = parse_source(
        source,
        module_id="pkg/api.py",
        package_parts=("pkg",),
        known_modules={"pkg.core": "pkg/core.py"},
    )
    ids = {node.id for node in parsed.nodes}
    assert "pkg/api.py::Child" in ids
    assert "pkg/api.py::Child::run" in ids
    assert all(node.kind is NodeKind.SYMBOL for node in parsed.nodes)

    method = next(node for node in parsed.nodes if node.id.endswith("::run"))
    assert "egress:http" in method.tags
    assert "untyped" in method.tags

    kinds = {edge.kind for edge in parsed.edges}
    assert EdgeKind.IMPORT in kinds
    assert EdgeKind.INHERIT in kinds
    assert EdgeKind.HTTP in kinds
    assert any(edge.target == EXTERNAL_ID for edge in parsed.edges)


def test_ingress_decorator_marks_receptor() -> None:
    source = """\
from fastapi import FastAPI
app = FastAPI()

@app.get("/healthz")
def health() -> str:
    return "ok"
"""
    parsed = parse_source(source, module_id="api.py")
    function = next(node for node in parsed.nodes if node.id == "api.py::health")
    assert "ingress" in function.tags
    assert "untyped" not in function.tags


def test_probe_detects_global_state_coupling() -> None:
    source = """\
_cache = {}

def update_cache(k: str, v: str) -> None:
    global _cache
    _cache[k] = v
"""
    parsed = parse_source(source, module_id="cache.py")
    fn = next(node for node in parsed.nodes if node.id == "cache.py::update_cache")
    assert "global_state" in fn.tags
    assert "tight_coupling" in fn.tags


def test_probe_detects_uninjectable_class_dependency() -> None:
    source = """\
class OrderProcessor:
    def __init__(self):
        pass

    def process(self, order_id: str):
        repo = OrderRepository()
        gateway = PaymentGateway()
        return repo.save(order_id)
"""
    parsed = parse_source(source, module_id="order.py")
    cls_node = next(node for node in parsed.nodes if node.id == "order.py::OrderProcessor")
    assert "uninjected_dependency" in cls_node.tags
    assert "tight_coupling" in cls_node.tags


def test_probe_permits_injected_dependencies() -> None:
    source = """\
class OrderProcessor:
    def __init__(self, repo: OrderRepository, gateway: PaymentGateway):
        self.repo = repo
        self.gateway = gateway

    def process(self, order_id: str):
        return self.repo.save(order_id)
"""
    parsed = parse_source(source, module_id="order.py")
    cls_node = next(node for node in parsed.nodes if node.id == "order.py::OrderProcessor")
    assert "uninjected_dependency" not in cls_node.tags
