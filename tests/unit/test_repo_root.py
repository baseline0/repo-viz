"""REPO_ROOT resolves to this repository, so every module can import it instead of computing paths."""

from repo_viz.constants import REPO_ROOT


def test_repo_root_contains_pyproject() -> None:
    assert (REPO_ROOT / "pyproject.toml").is_file()


def test_repo_root_contains_package() -> None:
    assert (REPO_ROOT / "src" / "repo_viz").is_dir()
