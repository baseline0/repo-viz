"""Git-backed producers and the tracked indicator configuration."""

from __future__ import annotations

import subprocess
from pathlib import Path

from repo_viz.constants import REPO_ROOT
from repo_viz.indicators.producers import cochange_from_git
from repo_viz.indicators.registry import validate_config
from repo_viz.indicators.spec import load_config


def _commit(root: Path, files: dict[str, str], message: str) -> None:
    for name, content in files.items():
        (root / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-q", "-m", message],
        cwd=root,
        check=True,
    )


def test_cochange_from_git_reads_recent_commits(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    _commit(tmp_path, {"a.py": "x = 1\n", "b.py": "y = 2\n"}, "first")
    _commit(tmp_path, {"b.py": "y = 3\n", "c.py": "z = 4\n"}, "second")

    counts = cochange_from_git(tmp_path, days=30)
    assert counts["b.py"] >= 2
    assert counts["a.py"] >= 1
    assert counts["c.py"] >= 1


def test_tracked_config_carries_evidence_and_resolves() -> None:
    config = load_config(REPO_ROOT / "config" / "indicators.toml")
    report = validate_config(config)
    assert report["ok"] is True
    assert report["indicators"] >= 14
    new_slots = {"arch_drift", "cognitive_friction", "cochange"}
    evidence = {item.id: item.evidence for item in config.indicators}
    assert all(evidence[slot] for slot in new_slots)
