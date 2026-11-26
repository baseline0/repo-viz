"""Human-authorized work-item request artifacts derived from an audit report.

## Specification Map

- ``build_work_item_payload`` — pure function; never writes to the canonical queue.
- ``write_work_item`` — writes JSON and a canonical-shape YAML draft to a scratch/data directory.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml

from repo_viz.audit import AuditReport

STATUS = "idea"  # the owner authorizes; this repo never marks an item authorized
REPO = "repo-viz"


def build_work_item_payload(
    report: AuditReport,
    *,
    snapshot: str,
    results: str,
) -> dict[str, Any]:
    """Build a self-contained request an operator can turn into a canonical WorkItem."""
    digest = hashlib.sha256(report.node_id.encode()).hexdigest()[:12]
    actions = list(report.suggested_actions) or ["Confirm the component needs no change."]
    prompt = (
        f"Audit-driven change for {report.node_label} ({report.node_id}). "
        + " ".join(actions)
        + f" Evidence: {snapshot}, {results}."
    )
    high = sum(1 for item in report.findings if item.severity == "high")
    medium = sum(1 for item in report.findings if item.severity == "medium")
    return {
        "id": f"rv-{digest}",
        "status": STATUS,
        "repo": REPO,
        "prompt": prompt,
        "objective": f"Resolve the audit findings for {report.node_label}.",
        "acceptance_criteria": [
            f"Resolve or explicitly defer all {high} high and {medium} medium findings.",
            "Regenerate the repo-viz snapshot and indicator results for the changed component.",
            "just ci passes in repo-viz.",
        ],
        "allowed_paths": [report.path or report.node_id],
        "evidence": {
            "snapshot": snapshot,
            "indicators": results,
            "source_commit": report.source_commit,
            "node_id": report.node_id,
        },
        "metrics": report.metrics,
        "findings": [
            {
                "indicator_id": item.indicator_id,
                "state": item.state.value,
                "severity": item.severity,
                "value": item.value,
                "evidence": item.evidence,
                "action": item.action,
            }
            for item in report.findings
        ],
        "gate": None,
        "gate_repo": None,
        "gate_hash": None,
        "gate_note": "Owner supplies the pinned gate command and hash before authorizing this item.",
        "schema": "repo-viz/work-item-request@1",
    }


def write_work_item(payload: dict[str, Any], out_dir: Path) -> dict[str, str]:
    """Write both representations atomically and return their paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "work-item.json"
    yaml_path = out_dir / "work-item.yaml"
    json_tmp = json_path.with_name(f".{json_path.name}.tmp")
    yaml_tmp = yaml_path.with_name(f".{yaml_path.name}.tmp")
    json_tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    yaml_tmp.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    os.replace(json_tmp, json_path)
    os.replace(yaml_tmp, yaml_path)
    return {"json": str(json_path), "yaml": str(yaml_path)}
