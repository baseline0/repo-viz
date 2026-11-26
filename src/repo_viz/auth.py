"""Constant-time API authentication for the repo-viz service.

## Specification Map

- ``authorize`` — returns an error status for protected routes, or None to continue.
- Probes and static assets are public; every ``/api/*`` route is protected.
"""

from __future__ import annotations

import hmac
import json
import os
from collections.abc import Mapping

TOOL_NAME = "repo-viz"


def _key_table() -> dict[str, dict[str, object]]:
    raw = os.environ.get("FLEET_API_KEYS")
    if not raw:
        path = os.environ.get("FLEET_API_KEYS_FILE")
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                raw = handle.read()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def authorize(method: str, path: str, headers: Mapping[str, str]) -> tuple[int, str] | None:
    """Authorize a request; 401 missing/invalid, 403 forbidden, 503 fail-closed."""
    if not (path.startswith("/api/") or path == "/mcp"):
        return None
    token = headers.get("authorization", "")
    prefix = "bearer "
    if token.lower().startswith(prefix):
        token = token[len(prefix) :]
    master = os.environ.get("FLEET_API_KEY", "")
    table = _key_table()

    if master and hmac.compare_digest(token, master):
        return None

    entry: dict[str, object] | None = None
    for key, value in table.items():
        if isinstance(value, dict) and hmac.compare_digest(token, key):
            entry = value
    if entry is not None:
        allowed = entry.get("allowed_tools", ["*"])
        if isinstance(allowed, list) and allowed != ["*"] and TOOL_NAME not in allowed:
            return 403, "tool not allowed"
        if entry.get("read_only") and method != "GET":
            return 403, "read-only key cannot write"
        return None

    if os.environ.get("FLEET_REQUIRE_AUTH") == "1" and not master and not table:
        return 503, "auth is required but no keys are configured"
    return 401, "missing or invalid API key"
