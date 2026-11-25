"""Hierarchy construction and git-backed source discovery.

## Specification Map

- ``module_dotted`` — repo-relative path to importable dotted module name.
- ``build_hierarchy`` — root, directory membranes and file cells from tracked paths.
- ``list_python_files`` — tracked ``*.py`` files, ignoring whatever git ignores.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path

from repo_viz.model import ROOT_ID, Node, NodeKind


def module_dotted(rel_path: str) -> str:
    """Return the dotted module name for a repo-relative ``.py`` path."""
    parts = rel_path.replace("\\", "/").removesuffix(".py").split("/")
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def build_hierarchy(rel_paths: Iterable[str], repo_label: str = "repo") -> tuple[Node, ...]:
    """Build the root, every directory membrane, and every file cell exactly once."""
    paths = sorted(rel_paths)
    nodes: dict[str, Node] = {
        ROOT_ID: Node(id=ROOT_ID, label=repo_label, kind=NodeKind.MEMBRANE, lod_rank=0),
        "external": Node(
            id="external",
            label="external systems",
            kind=NodeKind.MEMBRANE,
            parent=ROOT_ID,
            lod_rank=1,
            tags=frozenset({"external"}),
        ),
    }
    packages = {("/".join(path.split("/")[:-1])) for path in paths if path.endswith("__init__.py")}
    for path in paths:
        parts = path.split("/")
        for depth in range(1, len(parts)):
            membrane_id = "/".join(parts[:depth])
            parent = "/".join(parts[: depth - 1]) if depth > 1 else ROOT_ID
            if membrane_id not in nodes:
                tags = frozenset({"package"}) if membrane_id in packages else frozenset()
                nodes[membrane_id] = Node(
                    id=membrane_id,
                    label=parts[depth - 1],
                    kind=NodeKind.MEMBRANE,
                    parent=parent,
                    lod_rank=min(depth, 4),
                    tags=tags,
                )
        file_id = path
        parent = "/".join(parts[:-1]) if len(parts) > 1 else ROOT_ID
        nodes[file_id] = Node(
            id=file_id,
            label=parts[-1],
            kind=NodeKind.FILE,
            parent=parent,
            lod_rank=min(len(parts), 4),
            path=path,
        )
    return tuple(nodes[node_id] for node_id in sorted(nodes))


def module_index(nodes: Iterable[Node]) -> dict[str, str]:
    """Map dotted module names to file node ids for import resolution."""
    return {
        module_dotted(str(node.path)): node.id for node in nodes if node.kind is NodeKind.FILE and node.path is not None
    }


def list_python_files(repo_root: Path) -> tuple[str, ...]:
    """List tracked Python files; fall back to a filesystem walk outside git."""
    result = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return tuple(
            path.as_posix()
            for path in repo_root.rglob("*.py")
            if ".git" not in path.parts and ".venv" not in path.parts
        )
    return tuple(item for item in result.stdout.decode("utf-8").split("\0") if item)


def git_output(repo_root: Path, *args: str) -> str:
    """Run a read-only git command and return stdout, or an empty string on failure."""
    result = subprocess.run(["git", *args], cwd=repo_root, capture_output=True, check=False)
    return result.stdout.decode("utf-8", errors="replace") if result.returncode == 0 else ""
