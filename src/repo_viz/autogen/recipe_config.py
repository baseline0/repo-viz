"""Recipe naming for a repo: read and validate `just/recipes.toml`, and the error type the generator raises."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

RECIPES_CONFIG_NAME = "recipes.toml"


PREFIX_PATTERN = re.compile(r"^[a-z][a-z0-9]*$")


RECIPE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class EndpointRecipeError(Exception):
    """A typer app or its recipe config cannot be turned into recipes (for example, two recipes share a name)."""


@dataclass(frozen=True)
class RecipeConfig:
    """Recipe naming for one repo, read from `just/recipes.toml`.

    `default_prefix` names every endpoint recipe; `modules` maps a module name (the module that defines the
    command) to a prefix that overrides the default for that module. `names` maps a command name to an exact
    recipe name: that recipe is named as written, with no prefix.
    """

    default_prefix: str
    modules: Mapping[str, str]
    names: Mapping[str, str] = field(default_factory=dict)

    def prefix_for(self, module: str) -> str:
        """The recipe prefix for a command defined in `module`."""
        return self.modules.get(module, self.default_prefix)

    def recipe_name(self, module: str, command: str) -> str:
        """The recipe name for `command`: its exact `[names]` entry, else `<prefix>-<command>`."""
        if command in self.names:
            return self.names[command]
        return f"{self.prefix_for(module)}-{command}"


def _valid_prefix(value: object, where: str, config_path: Path) -> str:
    """Return `value` if it is a usable prefix, else raise with guidance."""
    if not isinstance(value, str) or not PREFIX_PATTERN.fullmatch(value):
        raise EndpointRecipeError(
            f"{where} in {config_path} is {value!r}; a recipe prefix must be lowercase letters and digits "
            "starting with a letter, matching ^[a-z][a-z0-9]*$ (for example: cto)"
        )
    return value


def load_recipe_config(config_path: Path) -> RecipeConfig:
    """Read and validate `config_path` (`just/recipes.toml`).

    Raises:
        EndpointRecipeError: If the file is missing, unparseable, has unknown keys, or has an invalid prefix.
    """
    if not config_path.exists():
        raise EndpointRecipeError(
            f'{config_path} is missing; create it with a line such as default_prefix = "cto" '
            "(the prefix for every endpoint recipe in this repo), and optionally a [modules] table "
            "mapping a module name to its own prefix, and optionally a [names] table mapping a command name "
            "to an exact recipe name"
        )
    try:
        data = tomllib.loads(config_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise EndpointRecipeError(f"{config_path} is not valid TOML: {exc}") from exc

    unknown = sorted(set(data) - {"default_prefix", "modules", "names"})
    if unknown:
        raise EndpointRecipeError(f"{config_path} has unknown keys {unknown}; allowed: default_prefix, modules, names")
    if "default_prefix" not in data:
        raise EndpointRecipeError(f'{config_path} must set default_prefix = "<prefix>"')
    default_prefix = _valid_prefix(data["default_prefix"], "default_prefix", config_path)

    raw_modules = data.get("modules", {})
    if not isinstance(raw_modules, dict):
        raise EndpointRecipeError(f"[modules] in {config_path} must be a table of module = prefix")
    modules = {
        str(module): _valid_prefix(prefix, f"[modules] {module}", config_path) for module, prefix in raw_modules.items()
    }
    raw_names = data.get("names", {})
    if not isinstance(raw_names, dict):
        raise EndpointRecipeError(f"[names] in {config_path} must be a table of command = recipe name")
    names = {str(command): _valid_recipe_name(name, command, config_path) for command, name in raw_names.items()}
    return RecipeConfig(default_prefix=default_prefix, modules=modules, names=names)


def _valid_recipe_name(value: object, command: str, config_path: Path) -> str:
    """Return `value` if it is a usable exact recipe name for `command`, else raise with guidance."""
    if not isinstance(value, str) or not RECIPE_NAME_PATTERN.match(value):
        raise EndpointRecipeError(
            f"[names] {command} in {config_path} is {value!r}; a recipe name must be lowercase letters, digits, "
            "'-' or '_', starting with a letter, matching ^[a-z][a-z0-9_-]*$"
        )
    return value


def recipes_config_path(generated_path: Path) -> Path:
    """The recipe config for a generated file: `recipes.toml` in the same directory (normally `just/`)."""
    return generated_path.parent / RECIPES_CONFIG_NAME
