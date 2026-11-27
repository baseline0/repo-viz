"""Generated interface files are current and free of fleet imports."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from repo_viz.autogen.cli import app as autogen_app
from repo_viz.autogen.endpoint_recipes import check_generated
from repo_viz.constants import REPO_ROOT

GENERATED = REPO_ROOT / "just" / "generated.just"
ROUTES = REPO_ROOT / "src" / "repo_viz" / "api_routes_autogen.py"


def test_generated_recipes_match_the_typer_app() -> None:
    assert check_generated(GENERATED, "repo_viz.cli", "app", include_base=False) is None


def test_generated_routes_have_no_fleet_imports() -> None:
    assert "fleet_base" not in ROUTES.read_text(encoding="utf-8")


def test_generated_routes_match_the_typer_app() -> None:
    result = CliRunner().invoke(autogen_app, ["check-api"])
    assert result.exit_code == 0, result.output


def test_check_endpoints_fails_on_a_stale_file(tmp_path: Path) -> None:
    (tmp_path / "recipes.toml").write_text('default_prefix = "rv"\n', encoding="utf-8")
    stale = tmp_path / "generated.just"
    stale.write_text("# stale\n", encoding="utf-8")
    result = CliRunner().invoke(
        autogen_app,
        ["check-endpoints", "--output", str(stale)],
    )
    assert result.exit_code == 1
