"""Producers fill ``EvaluationContext.values`` from a checkout.

## Specification Map

- ``satd_from_source`` — pure tokenize-based counter of debt markers in comments.
- ``satd_counts`` — maps repo-relative file paths to marker counts.
"""

from __future__ import annotations

import io
import re
import subprocess
import tokenize
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

_MARKER = re.compile(r"\b(TODO|FIXME|HACK|XXX|BUG)\b")


def satd_from_source(source: str) -> int:
    """Count debt markers in comment tokens only; string literals never count."""
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        return sum(len(_MARKER.findall(token.string)) for token in tokens if token.type == tokenize.COMMENT)
    except tokenize.TokenError:
        return 0


def cochange_counts(commits: Iterable[Iterable[str]]) -> dict[str, float]:
    """Count co-edit partners per file from a sequence of commit file lists."""
    counts: dict[str, float] = defaultdict(float)
    for commit in commits:
        files = sorted(set(commit))
        for index, left in enumerate(files):
            for right in files[index + 1 :]:
                counts[left] += 1
                counts[right] += 1
    return dict(counts)


def cochange_from_git(repo_root: Path, *, days: int = 30) -> dict[str, float]:
    """Count co-changes from recent git commits; only Python paths are considered."""
    completed = subprocess.run(
        ["git", "log", f"--since={days} days ago", "--format=%x00", "--name-only"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return {}
    commits = [
        tuple(line for line in chunk.splitlines() if line.strip().endswith(".py"))
        for chunk in completed.stdout.decode("utf-8", errors="replace").split("\0")
    ]
    return cochange_counts(commits)


def collect_values(
    repo_root: Path,
    rel_paths: Iterable[str],
    *,
    days: int = 30,
) -> dict[str, dict[str, float]]:
    """Build every producer's value map for one checkout."""
    return {
        "satd": satd_counts(repo_root, rel_paths),
        "cochange": cochange_from_git(repo_root, days=days),
    }


def satd_counts(repo_root: Path, rel_paths: Iterable[str]) -> dict[str, float]:
    """Count SATD markers for each tracked Python file."""
    result: dict[str, float] = {}
    for rel_path in rel_paths:
        source = (repo_root / rel_path).read_text(encoding="utf-8", errors="ignore")
        count = satd_from_source(source)
        if count:
            result[rel_path] = float(count)
    return result
