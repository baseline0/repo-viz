"""Producers fill ``EvaluationContext.values`` from a checkout.

## Specification Map

- ``satd_from_source`` — pure tokenize-based counter of debt markers in comments.
- ``satd_counts`` — maps repo-relative file paths to marker counts.
"""

from __future__ import annotations

import io
import re
import tokenize
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


def collect_values(repo_root: Path, rel_paths: Iterable[str]) -> dict[str, dict[str, float]]:
    """Build every producer's value map for one checkout."""
    return {"satd": satd_counts(repo_root, rel_paths)}


def satd_counts(repo_root: Path, rel_paths: Iterable[str]) -> dict[str, float]:
    """Count SATD markers for each tracked Python file."""
    result: dict[str, float] = {}
    for rel_path in rel_paths:
        source = (repo_root / rel_path).read_text(encoding="utf-8", errors="ignore")
        count = satd_from_source(source)
        if count:
            result[rel_path] = float(count)
    return result
