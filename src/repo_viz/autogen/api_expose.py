"""Exposure decorator understood by both copied generators.

## Specification Map

- ``expose`` — marks a Typer callback as an unsecured API route; auth is enforced
  centrally by the FastAPI middleware, not per route.
- ``EXPOSE_DECORATOR_NAMES`` / ``EXPOSED_KEYS`` — constants the AST generator reads.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

EXPOSED_KEYS = (
    "path",
    "method",
    "access_level",
    "risk_level",
    "requires_audit",
    "rate_limit",
    "description",
)
EXPOSE_DECORATOR_NAMES = ("expose_api_secure", "expose")

_F = TypeVar("_F", bound=Callable[..., Any])


def expose(path: str, method: str = "POST", **metadata: Any) -> Callable[[_F], _F]:
    """Declare a Typer callback as an API route at ``path``."""
    allowed = set(EXPOSED_KEYS) - {"path", "method"}

    def decorate(function: _F) -> _F:
        unknown = set(metadata) - allowed
        if unknown:
            raise ValueError(f"unknown exposure keys: {sorted(unknown)}")
        values: dict[str, Any] = {"path": path, "method": method, "secured": False}
        values.update(metadata)
        function.__api_expose__ = values  # type: ignore[attr-defined]
        return function

    return decorate
