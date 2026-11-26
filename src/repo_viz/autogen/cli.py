"""Local wrapper around the copied generators: recipes and API routes.

## Specification Map

- ``generate-endpoints`` / ``check-endpoints`` — just/generated.just from the Typer app.
- ``gen-api`` / ``check-api`` — src/repo_viz/api_routes_autogen.py from the same app.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import typer

from repo_viz.autogen.endpoint_recipes import check_generated, write_generated
from repo_viz.autogen.fastapi_autogen import generate_routes_file
from repo_viz.constants import REPO_ROOT

app = typer.Typer(add_completion=False, no_args_is_help=True)

DEFAULT_OUTPUT = REPO_ROOT / "just" / "generated.just"
DEFAULT_ROUTES = REPO_ROOT / "src" / "repo_viz" / "api_routes_autogen.py"


@app.command()
def generate_endpoints(
    module: str = typer.Option("repo_viz.cli", "--module"),
    app_name: str = typer.Option("app", "--app"),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output"),
) -> None:
    """Generate just recipes from the Typer app."""
    written = write_generated(output, module, app_name, include_base=False)
    typer.echo(f"wrote {output}" if written else f"{output} is current")


@app.command()
def check_endpoints(
    module: str = typer.Option("repo_viz.cli", "--module"),
    app_name: str = typer.Option("app", "--app"),
    output: Path = typer.Option(DEFAULT_OUTPUT, "--output"),
) -> None:
    """Fail when the committed just recipes are stale."""
    problem = check_generated(output, module, app_name, include_base=False)
    if problem is not None:
        typer.echo(problem, err=True)
        raise typer.Exit(1)
    typer.echo(f"{output} is current")


@app.command()
def gen_api(
    app_path: str = typer.Option("repo_viz.cli:app", "--app"),
    output: Path = typer.Option(DEFAULT_ROUTES, "--output"),
    prefix: str = typer.Option("/api/v1", "--prefix"),
) -> None:
    """Generate FastAPI routes from the Typer app."""
    generate_routes_file(app_path, output, prefix=prefix, repo=REPO_ROOT)
    typer.echo(f"wrote {output}")


@app.command()
def check_api(
    app_path: str = typer.Option("repo_viz.cli:app", "--app"),
    output: Path = typer.Option(DEFAULT_ROUTES, "--output"),
    prefix: str = typer.Option("/api/v1", "--prefix"),
) -> None:
    """Fail when the committed route module differs from a fresh generation."""
    with tempfile.TemporaryDirectory() as scratch:
        generated = Path(scratch) / output.name
        generate_routes_file(app_path, generated, prefix=prefix, repo=REPO_ROOT)
        if not output.is_file() or output.read_text() != generated.read_text():
            typer.echo(f"{output} is stale; run gen-api", err=True)
            raise typer.Exit(1)
    typer.echo(f"{output} is current")


if __name__ == "__main__":
    app()
