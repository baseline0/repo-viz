"""Review-facing digests are canonical, provenance-bearing and read-only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from repo_viz.cli import app
from repo_viz.review_digests import (
    AUDIT_EXCLUDED_FIELDS,
    GRAPH_EXCLUDED_FIELDS,
    INDICATOR_EXCLUDED_FIELDS,
    REVIEW_DIGEST_SCHEMA,
    build_review_digest_bundle,
    canonical_config_digest,
    canonical_digest,
)


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _graph(analyzed_at: str = "2026-01-01T00:00:00+00:00", loc: int = 7) -> dict[str, Any]:
    return {
        "schema": "repo-viz/graph@1",
        "source_repo": "sample",
        "source_commit": "abc123",
        "analyzed_at": analyzed_at,
        "nodes": [{"id": "pkg/a.py", "metrics": {"loc": loc}}],
        "edges": [],
        "ports": [],
    }


def _indicators(
    computed_at: str = "2026-01-01T00:00:01+00:00",
    trigger: str = "render",
    evidence: str = "pkg/a.py:1",
) -> dict[str, Any]:
    return {
        "version": 1,
        "results": [
            {
                "indicator_id": "boundary",
                "node_id": "pkg/a.py",
                "trigger": trigger,
                "state": "violation",
                "value": 3,
                "evidence": evidence,
                "computed_at": computed_at,
            }
        ],
    }


def _audit(created_at: str = "2026-01-01T00:00:02+00:00", evidence: str = "pkg/a.py:1") -> dict[str, Any]:
    return {
        "node_id": "pkg/a.py",
        "node_label": "a.py",
        "path": "pkg/a.py",
        "source_commit": "abc123",
        "metrics": {"loc": 7},
        "findings": [
            {
                "indicator_id": "boundary",
                "state": "violation",
                "severity": "high",
                "value": 3,
                "evidence": evidence,
                "action": "Replace the private import.",
            }
        ],
        "suggested_actions": ["Replace the private import."],
        "created_at": created_at,
        "schema": "repo-viz/audit@1",
    }


def _artifacts(tmp_path: Path, suffix: str = "") -> tuple[Path, Path, Path]:
    graph = _write_json(tmp_path / f"graph{suffix}.json", _graph())
    results = _write_json(tmp_path / f"indicators{suffix}.json", _indicators())
    audit = _write_json(tmp_path / f"audit{suffix}.json", _audit())
    return graph, results, audit


def test_canonical_digest_follows_the_adr_rule() -> None:
    value = {"b": 2, "a": {"d": 4, "c": 3}}
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert canonical_digest(value) == f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def test_equal_digests_when_only_volatile_fields_differ(tmp_path: Path) -> None:
    first_graph, first_results, first_audit = _artifacts(tmp_path, "-first")
    second_graph = _write_json(
        tmp_path / "graph-second.json",
        _graph(analyzed_at="2026-06-09T12:00:00+00:00"),
    )
    second_results = _write_json(
        tmp_path / "indicators-second.json",
        _indicators(computed_at="2026-06-09T12:00:01+00:00"),
    )
    second_audit = _write_json(
        tmp_path / "audit-second.json",
        _audit(created_at="2026-06-09T12:00:02+00:00"),
    )

    first = build_review_digest_bundle(first_graph, first_results, audit_path=first_audit)
    second = build_review_digest_bundle(second_graph, second_results, audit_path=second_audit)

    assert first.graph.digest == second.graph.digest
    assert first.indicators.digest == second.indicators.digest
    assert first.audit is not None and second.audit is not None
    assert first.audit.digest == second.audit.digest
    for digest in (first.graph.digest, first.indicators.digest, first.audit.digest):
        assert digest.startswith("sha256:")
        assert len(digest) == len("sha256:") + 64


def test_non_volatile_content_still_changes_the_digest(tmp_path: Path) -> None:
    graph, results, audit = _artifacts(tmp_path, "-base")
    base = build_review_digest_bundle(graph, results, audit_path=audit)

    changed_graph = _write_json(tmp_path / "graph-changed.json", _graph(loc=11))
    changed_results = _write_json(tmp_path / "indicators-changed.json", _indicators(evidence="pkg/b.py:9"))
    changed_audit = _write_json(tmp_path / "audit-changed.json", _audit(evidence="pkg/b.py:9"))
    changed = build_review_digest_bundle(changed_graph, changed_results, audit_path=changed_audit)

    assert changed.graph.digest != base.graph.digest
    assert changed.indicators.digest != base.indicators.digest
    assert changed.audit is not None and base.audit is not None
    assert changed.audit.digest != base.audit.digest


def test_own_digest_field_is_omitted(tmp_path: Path) -> None:
    clean_graph, clean_results, clean_audit = _artifacts(tmp_path, "-clean")
    stale = "sha256:" + "0" * 64
    dirty_graph = _graph()
    dirty_graph["digest"] = stale
    dirty_results = _indicators()
    dirty_results["digest"] = stale
    dirty_audit = _audit()
    dirty_audit["digest"] = stale
    graph = _write_json(tmp_path / "graph-dirty.json", dirty_graph)
    results = _write_json(tmp_path / "indicators-dirty.json", dirty_results)
    audit = _write_json(tmp_path / "audit-dirty.json", dirty_audit)

    clean = build_review_digest_bundle(clean_graph, clean_results, audit_path=clean_audit)
    dirty = build_review_digest_bundle(graph, results, audit_path=audit)

    assert dirty.graph.digest == clean.graph.digest
    assert dirty.indicators.digest == clean.indicators.digest
    assert dirty.audit is not None and clean.audit is not None
    assert dirty.audit.digest == clean.audit.digest


def test_report_records_paths_commits_trigger_config_and_exclusions(tmp_path: Path) -> None:
    graph, results, audit = _artifacts(tmp_path)
    config = tmp_path / "indicators.toml"
    config.write_text('version = 1\n\n[[indicators]]\nid = "boundary"\nenabled = true\n', encoding="utf-8")

    bundle = build_review_digest_bundle(graph, results, audit_path=audit, config_path=config, trigger="change")
    payload = bundle.to_dict()

    assert payload["schema"] == REVIEW_DIGEST_SCHEMA
    assert payload["config_digest"] == canonical_config_digest(config)
    assert payload["config_digest"].startswith("sha256:")
    assert payload["config_path"] == str(config)
    assert payload["source_commit"] == "abc123"
    assert payload["trigger"] == "change"
    assert payload["graph"] == {
        "path": str(graph),
        "digest": bundle.graph.digest,
        "source_commit": "abc123",
        "excluded_fields": list(GRAPH_EXCLUDED_FIELDS),
        "schema": "repo-viz/graph@1",
    }
    assert payload["indicators"]["path"] == str(results)
    assert payload["indicators"]["version"] == 1
    assert payload["indicators"]["source_commit"] == "abc123"
    assert payload["indicators"]["trigger"] == "change"
    assert payload["indicators"]["excluded_fields"] == list(INDICATOR_EXCLUDED_FIELDS)
    assert payload["audit"] is not None
    assert payload["audit"]["path"] == str(audit)
    assert payload["audit"]["source_commit"] == "abc123"
    assert payload["audit"]["excluded_fields"] == list(AUDIT_EXCLUDED_FIELDS)


def test_trigger_is_inferred_from_indicator_rows(tmp_path: Path) -> None:
    graph, _, _ = _artifacts(tmp_path)
    single = _write_json(tmp_path / "single.json", _indicators(trigger="change"))
    mixed_payload = _indicators(trigger="render")
    mixed_payload["results"].append(
        {
            "indicator_id": "boundary",
            "node_id": "pkg/b.py",
            "trigger": "change",
            "state": "na",
            "value": None,
            "evidence": "none",
            "computed_at": "2026-06-09T12:00:03+00:00",
        }
    )
    mixed = _write_json(tmp_path / "mixed.json", mixed_payload)

    assert build_review_digest_bundle(graph, single).trigger == "change"
    assert build_review_digest_bundle(graph, single, trigger="render").trigger == "render"
    assert build_review_digest_bundle(graph, mixed).trigger is None


def test_invalid_trigger_is_rejected(tmp_path: Path) -> None:
    graph, results, _ = _artifacts(tmp_path)
    try:
        build_review_digest_bundle(graph, results, trigger="deploy")
    except ValueError as exc:
        assert "trigger must be one of" in str(exc)
    else:
        raise AssertionError("an unsupported trigger was accepted")


def test_review_digests_cli_is_read_only_and_emits_one_json_object(
    tmp_path: Path,
    cli_runner: CliRunner,
) -> None:
    graph, results, audit = _artifacts(tmp_path)
    before = sorted(path.name for path in tmp_path.iterdir())

    invoked = cli_runner.invoke(
        app,
        [
            "review-digests",
            "--snapshot",
            str(graph),
            "--results",
            str(results),
            "--audit",
            str(audit),
            "--json",
        ],
    )

    assert invoked.exit_code == 0, invoked.output
    payload = json.loads(invoked.output)
    assert payload["schema"] == REVIEW_DIGEST_SCHEMA
    assert payload["trigger"] == "render"
    assert payload["config_digest"] is None
    assert payload["audit"]["digest"].startswith("sha256:")
    assert sorted(path.name for path in tmp_path.iterdir()) == before
