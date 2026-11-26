"""The base set of python- recipes emitted into every repo, and how each one renders."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tool:
    """One way to run a base recipe: a presence probe and the command to run when it passes."""

    name: str
    probe: str
    run: str


@dataclass(frozen=True)
class BaseRecipe:
    """A recipe emitted into every repo. Tools are tried in order; the first present one runs."""

    name: str
    group: str
    doc: str
    tools: tuple[Tool, ...]


BASE_RECIPES: tuple[BaseRecipe, ...] = (
    BaseRecipe(
        name="python-fmt",
        group="python",
        doc="Format Python code (ruff format)",
        tools=(Tool(name="ruff", probe="uv run ruff --version", run="uv run ruff format ."),),
    ),
    BaseRecipe(
        name="python-lint",
        group="python",
        doc="Lint Python code without changing it (ruff check)",
        tools=(Tool(name="ruff", probe="uv run ruff --version", run="uv run ruff check ."),),
    ),
    BaseRecipe(
        name="python-check-types",
        group="python",
        doc="Type check src/ (pyright, else mypy)",
        tools=(
            Tool(name="pyright", probe="uv run pyright --version", run="uv run pyright src/"),
            Tool(name="mypy", probe="uv run mypy --version", run="uv run mypy src/"),
        ),
    ),
)


def _render_base(recipe: BaseRecipe) -> str:
    """Render one base recipe as a bash recipe that probes each tool in order."""
    lines = [
        f"# {recipe.doc}",
        f'[group("{recipe.group}")]',
        f"{recipe.name}:",
        "    #!/usr/bin/env bash",
        "    set -euo pipefail",
    ]
    for tool in recipe.tools:
        lines.append(f"    if {tool.probe} >/dev/null 2>&1; then")
        lines.append(f"        {tool.run}")
        lines.append("        exit 0")
        lines.append("    fi")
    names = " or ".join(tool.name for tool in recipe.tools)
    lines.append(
        f'    echo "error: {recipe.name} cannot run in this repo: install {names} as a dev dependency '
        f'(uv add --dev {recipe.tools[0].name})" >&2'
    )
    lines.append("    exit 1")
    return "\n".join(lines)
