"""Snapshot construction: pure core plus a git-backed convenience wrapper.

## Specification Map

- ``build_snapshot_from_sources`` — deterministic and hermetic; the unit-tested core.
- ``build_snapshot`` — reads tracked files and git churn from a real checkout.
- ``write_snapshot`` — atomic write of the derived JSON artifact.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from repo_viz.aggregate import aggregate
from repo_viz.discovery import build_hierarchy, git_output, list_python_files, module_index
from repo_viz.model import GraphSnapshot, Node
from repo_viz.parsers.python_ast import parse_source


def build_snapshot_from_sources(
    sources: Mapping[str, str],
    *,
    repo_label: str = "repo",
    source_commit: str = "",
    analyzed_at: str = "1970-01-01T00:00:00+00:00",
    churn: Mapping[str, int] | None = None,
) -> GraphSnapshot:
    """Build a snapshot from in-memory sources, with no filesystem or git access."""
    hierarchy = build_hierarchy(sources.keys(), repo_label)
    modules = module_index(hierarchy)
    churn_by_path = dict(churn or {})
    nodes = tuple(
        replace(node, metrics=replace(node.metrics, churn_30d=churn_by_path.get(str(node.path), 0)))
        if node.path is not None
        else node
        for node in hierarchy
    )
    symbols: list[Node] = []
    edges = []
    for path in sorted(sources):
        package_parts = tuple(path.split("/")[:-1])
        parsed = parse_source(
            sources[path],
            module_id=path,
            package_parts=package_parts,
            known_modules=modules,
        )
        symbols.extend(parsed.nodes)
        edges.extend(parsed.edges)
    result = aggregate(nodes + tuple(symbols), tuple(edges))
    return GraphSnapshot(
        source_repo=repo_label,
        source_commit=source_commit,
        analyzed_at=analyzed_at,
        nodes=result.nodes,
        edges=result.edges,
        ports=result.ports,
    )


def snapshot_counts(payload: Mapping[str, Any]) -> dict[str, int]:
    """Return artifact counts from a snapshot mapping; pure and JSON-ready."""
    return {
        "nodes": len(payload["nodes"]),
        "edges": len(payload["edges"]),
        "ports": len(payload["ports"]),
    }


def churn_counts(repo_root: Path, *, days: int) -> dict[str, int]:
    """Count tracked-file touches in the last ``days`` days."""
    log = git_output(repo_root, "log", f"--since={days} days ago", "--name-only", "--pretty=format:")
    return dict(Counter(line for line in log.splitlines() if line.endswith(".py")))


def build_snapshot(repo_root: Path, *, days: int = 30) -> GraphSnapshot:
    """Read a checkout and build its snapshot."""
    paths = list_python_files(repo_root)
    sources = {path: (repo_root / path).read_text(encoding="utf-8", errors="ignore") for path in paths}
    return build_snapshot_from_sources(
        sources,
        repo_label=repo_root.name,
        source_commit=git_output(repo_root, "rev-parse", "HEAD").strip(),
        analyzed_at=datetime.now(UTC).isoformat(),
        churn=churn_counts(repo_root, days=days),
    )


def write_snapshot(snapshot: GraphSnapshot, out_path: Path) -> None:
    """Atomically write the derived snapshot artifact."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.with_name(f".{out_path.name}.tmp")
    payload: dict[str, Any] = snapshot.to_dict()
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, out_path)
