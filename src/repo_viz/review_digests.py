"""Canonical, review-facing digests for repo-viz structural artifacts.

## Specification Map

- ``canonical_digest`` — sha256 of compact, key-sorted canonical JSON, with the artifact's own digest omitted.
- ``canonical_config_digest`` — the same digest rule applied to parsed indicator config TOML.
- ``build_review_digest_bundle`` — read graph/indicator/optional audit/config artifacts and compose a report.
- ``ReviewDigestBundle`` — the read-only ``repo-viz/review-digests@1`` report emitted by the CLI.

Volatile timestamps are excluded from digests, never from the source artifacts. The exclusion set is
``analyzed_at`` for graphs, ``results[*].computed_at`` for indicator rows and ``created_at`` for audits.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, cast

REVIEW_DIGEST_SCHEMA = "repo-viz/review-digests@1"
VALID_TRIGGERS = frozenset({"render", "change"})
GRAPH_EXCLUDED_FIELDS = ("analyzed_at",)
INDICATOR_EXCLUDED_FIELDS = ("results[*].computed_at",)
AUDIT_EXCLUDED_FIELDS = ("created_at",)


def canonical_digest(value: Mapping[str, Any]) -> str:
    """Return ``sha256:<hex>`` of canonical JSON with the artifact's own digest omitted."""
    payload = deepcopy(dict(value))
    payload.pop("digest", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _json_ready(value: Any) -> Any:
    """Make parsed TOML JSON-ready without changing scalar meaning."""
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def canonical_config_digest(config_path: Path) -> str:
    """Digest parsed indicator config as canonical JSON, so formatting and comments do not matter."""
    parsed = tomllib.loads(config_path.read_text(encoding="utf-8"))
    return canonical_digest(cast(dict[str, Any], _json_ready(parsed)))


def _load_json_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return cast(dict[str, Any], payload)


def _source_commit(payload: Mapping[str, Any], path: Path) -> str:
    commit = payload.get("source_commit")
    if not isinstance(commit, str) or not commit:
        raise ValueError(f"{path} has no source_commit")
    return commit


def _optional_schema(payload: Mapping[str, Any]) -> str | None:
    schema = payload.get("schema")
    return schema if isinstance(schema, str) else None


def _optional_version(payload: Mapping[str, Any]) -> str | int | None:
    version = payload.get("version")
    return version if isinstance(version, (str, int)) and not isinstance(version, bool) else None


def _effective_trigger(payload: Mapping[str, Any], trigger: str | None) -> str | None:
    if trigger is not None:
        if trigger not in VALID_TRIGGERS:
            raise ValueError(f"trigger must be one of {sorted(VALID_TRIGGERS)}")
        return trigger
    rows = payload.get("results", [])
    triggers = {
        row["trigger"]
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("trigger"), str) and row["trigger"] in VALID_TRIGGERS
    }
    return next(iter(triggers)) if len(triggers) == 1 else None


def _normalize_graph(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(dict(payload))
    for key in GRAPH_EXCLUDED_FIELDS:
        normalized.pop(key, None)
    return normalized


def _normalize_indicators(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(dict(payload))
    rows = normalized.get("results", [])
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                row.pop("computed_at", None)
    return normalized


def _normalize_audit(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(dict(payload))
    for key in AUDIT_EXCLUDED_FIELDS:
        normalized.pop(key, None)
    return normalized


@dataclass(frozen=True, slots=True)
class ArtifactDigest:
    """One source artifact's path, canonical digest and provenance."""

    path: str
    digest: str
    source_commit: str
    excluded_fields: tuple[str, ...]
    schema: str | None = None
    version: str | int | None = None
    trigger: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready mapping; optional fields are omitted when unknown."""
        payload: dict[str, Any] = {
            "path": self.path,
            "digest": self.digest,
            "source_commit": self.source_commit,
            "excluded_fields": list(self.excluded_fields),
        }
        if self.schema is not None:
            payload["schema"] = self.schema
        if self.version is not None:
            payload["version"] = self.version
        if self.trigger is not None:
            payload["trigger"] = self.trigger
        return payload


@dataclass(frozen=True, slots=True)
class ReviewDigestBundle:
    """A review-facing report of canonical digests for stored structural artifacts."""

    source_commit: str
    graph: ArtifactDigest
    indicators: ArtifactDigest
    config_digest: str | None = None
    config_path: str | None = None
    trigger: str | None = None
    audit: ArtifactDigest | None = None
    schema: str = REVIEW_DIGEST_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        """Return the ``repo-viz/review-digests@1`` payload."""
        return {
            "schema": self.schema,
            "config_digest": self.config_digest,
            "config_path": self.config_path,
            "source_commit": self.source_commit,
            "trigger": self.trigger,
            "graph": self.graph.to_dict(),
            "indicators": self.indicators.to_dict(),
            "audit": self.audit.to_dict() if self.audit is not None else None,
        }


def build_review_digest_bundle(
    snapshot_path: Path,
    results_path: Path,
    *,
    audit_path: Path | None = None,
    config_path: Path | None = None,
    trigger: str | None = None,
) -> ReviewDigestBundle:
    """Read artifacts and return canonical digests with only declared volatile fields omitted.

    Indicator results carry no source commit of their own, so their provenance records the paired
    graph's commit. The effective trigger comes from ``trigger`` or, when omitted, from a single
    trigger value shared by every indicator row (``None`` when rows mix triggers).
    """
    graph = _load_json_mapping(snapshot_path)
    indicators = _load_json_mapping(results_path)
    graph_commit = _source_commit(graph, snapshot_path)
    if not isinstance(indicators.get("results"), list):
        raise ValueError(f"{results_path} has no results list")
    effective_trigger = _effective_trigger(indicators, trigger)

    graph_digest = ArtifactDigest(
        path=str(snapshot_path),
        digest=canonical_digest(_normalize_graph(graph)),
        source_commit=graph_commit,
        excluded_fields=GRAPH_EXCLUDED_FIELDS,
        schema=_optional_schema(graph),
    )
    indicator_digest = ArtifactDigest(
        path=str(results_path),
        digest=canonical_digest(_normalize_indicators(indicators)),
        source_commit=graph_commit,
        excluded_fields=INDICATOR_EXCLUDED_FIELDS,
        version=_optional_version(indicators),
        trigger=effective_trigger,
    )

    audit_digest: ArtifactDigest | None = None
    if audit_path is not None:
        audit = _load_json_mapping(audit_path)
        audit_digest = ArtifactDigest(
            path=str(audit_path),
            digest=canonical_digest(_normalize_audit(audit)),
            source_commit=_source_commit(audit, audit_path),
            excluded_fields=AUDIT_EXCLUDED_FIELDS,
            schema=_optional_schema(audit),
        )

    return ReviewDigestBundle(
        source_commit=graph_commit,
        graph=graph_digest,
        indicators=indicator_digest,
        config_digest=canonical_config_digest(config_path) if config_path is not None else None,
        config_path=str(config_path) if config_path is not None else None,
        trigger=effective_trigger,
        audit=audit_digest,
    )


__all__ = [
    "AUDIT_EXCLUDED_FIELDS",
    "GRAPH_EXCLUDED_FIELDS",
    "INDICATOR_EXCLUDED_FIELDS",
    "REVIEW_DIGEST_SCHEMA",
    "VALID_TRIGGERS",
    "ArtifactDigest",
    "ReviewDigestBundle",
    "build_review_digest_bundle",
    "canonical_config_digest",
    "canonical_digest",
]
