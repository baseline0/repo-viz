"""Shared pytest configuration and fixtures for repo-viz.

Tier folders are tests/unit, tests/integration, tests/contract, tests/host and
tests/e2e. The marker comes from the folder, never from a hand-written marker.

## Fixtures

- ``sample_sources`` — in-memory modules for hermetic parser tests.
- ``sample_snapshot`` — snapshot built from those sources, no filesystem.
- ``sample_config`` — indicator config built in memory, no config-file read.
- ``tmp_repo`` — a committed temporary git checkout for integration tests.
- ``cli_runner`` — Typer's in-process CLI runner.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from repo_viz.indicators.spec import Arc, Indicator, IndicatorConfig, State
from repo_viz.snapshot import build_snapshot_from_sources

TESTS_ROOT = Path(os.path.dirname(os.path.abspath(__file__)))
DIRECTORY_MARKERS = {
    "unit": "unit",
    "integration": "integration",
    "contract": "contract",
    "host": "host",
    "e2e": "e2e",
}


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Add the marker that matches each test's top-level tier folder."""
    for item in items:
        try:
            relative = Path(str(item.fspath)).resolve().relative_to(TESTS_ROOT)
        except ValueError:
            continue
        if relative.parts and relative.parts[0] in DIRECTORY_MARKERS:
            item.add_marker(getattr(pytest.mark, DIRECTORY_MARKERS[relative.parts[0]]))


@pytest.fixture
def sample_sources() -> dict[str, str]:
    """Return two in-memory modules with an import, a decorator and a sink."""
    return {
        "pkg/core.py": "class Engine:\n    pass\n",
        "pkg/api.py": (
            "import httpx\n"
            "from .core import Engine\n\n"
            "class Child(Engine):\n"
            "    def run(self):\n"
            "        return httpx.get('https://example.test')\n"
        ),
    }


@pytest.fixture
def sample_snapshot(sample_sources: dict[str, str]) -> object:
    """Return a versioned snapshot built entirely in memory."""
    return build_snapshot_from_sources(sample_sources, repo_label="sample", analyzed_at="now")


@pytest.fixture
def sample_config() -> IndicatorConfig:
    """Return a minimal two-slot config, independent of the tracked TOML."""
    colors = dict.fromkeys(State, "#000000")
    return IndicatorConfig(
        1,
        Arc(315, 45, 8, 320),
        (
            Indicator("security", "Security", "shield", 0, colors, "repo_viz.indicators.builtin:security"),
            Indicator("satd", "SATD", "bug", 1, colors, "repo_viz.indicators.builtin:satd", thresholds={"partial": 1}),
        ),
    )


@pytest.fixture
def cli_runner() -> CliRunner:
    """Return an in-process Typer CLI runner."""
    return CliRunner()


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a committed git checkout with a TODO marker and a cross-module import."""
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "core.py").write_text("def helper() -> int:\n    return 1\n", encoding="utf-8")
    (package / "api.py").write_text(
        "from .core import helper\n\n# TODO: replace with a real implementation\ndef call() -> int:\n    return helper()\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.test",
            "commit",
            "-q",
            "-m",
            "init",
        ],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path
