"""Walk a typer app and its nested groups to collect the endpoint recipes, with name checks."""

from __future__ import annotations

import ast
import copy
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from repo_viz.autogen.endpoint_params import RecipeParam, _recipe_params
from repo_viz.autogen.endpoint_source import (
    _keyword_literal,
    _Source,
    _Sources,
    read_exposed_arguments,
    resolve_module_file,
)
from repo_viz.autogen.recipe_config import EndpointRecipeError, RecipeConfig


@dataclass(frozen=True)
class EndpointRecipe:
    """A recipe generated from one endpoint command.

    `command` is the leaf command name (it names the recipe); `path` is the full invocation path, which is
    the enclosing group names followed by `command` (for example ("reports", "deploy")).
    """

    name: str
    prefix: str
    command: str
    path: tuple[str, ...]
    doc: str
    params: tuple[RecipeParam, ...]
    exposed: bool = False


DESTRUCTIVE_WORDS = frozenset(
    {"clear", "delete", "remove", "purge", "reset", "drop", "wipe", "prune", "teardown", "destroy"}
)


def _is_destructive(command: str) -> bool:
    """True when the command name has a verb that changes state, so the command needs an explicit --confirm."""
    return any(word in DESTRUCTIVE_WORDS for word in command.replace("_", "-").split("-"))


def _is_bare_command_app(src: _Source, var: str) -> bool:
    """True when Typer makes the app's only command the app itself, so that command takes no name token.

    Typer builds a plain command (no group) only for an app with exactly one command, no callback, and no nested
    groups (typer.main.get_command). Any other shape is a group, and its commands need their name.
    """
    call = src.typers.get(var)
    if call is not None and any(kw.arg == "callback" for kw in call.keywords):
        return False
    if src.registrations(var):
        return False
    for func in src.functions:
        for dec in func.decorator_list:
            target = dec.func if isinstance(dec, ast.Call) else dec
            if (
                isinstance(target, ast.Attribute)
                and target.attr == "callback"
                and isinstance(target.value, ast.Name)
                and target.value.id == var
            ):
                return False
    commands = [func for func in src.functions if src.command_name(func, var) is not None]
    return len(commands) + len(src.bound_commands_for(var)) == 1


def _registered_command_name(call: ast.Call, func: ast.FunctionDef, file: Path) -> str | None:
    """The command name a `<app>.command(...)` registration gives `func`: its name= literal, else the function's name."""
    where = f"{file}:{call.lineno} {func.name}"
    name = _keyword_literal(call, "name", where)
    if name is None:
        return func.name.replace("_", "-")
    if not isinstance(name, str):
        raise EndpointRecipeError(f"{where}: the command name must be a string")
    return name


def _without_self(func: ast.FunctionDef) -> ast.FunctionDef:
    """A copy of method `func` without its `self` argument, so the recipe reads only the command's own parameters."""
    trimmed = copy.copy(func)
    trimmed.args = copy.copy(func.args)
    trimmed.args.args = func.args.args[1:]
    return trimmed


def _collect(
    src: _Source,
    var: str,
    group_path: tuple[str, ...],
    sources: _Sources,
    config: RecipeConfig,
    found: list[EndpointRecipe],
    active: frozenset[tuple[str, str]],
    bare_app: bool = False,
) -> None:
    """Append the endpoints of typer app `var` in `src`, and of its nested groups, to `found`.

    `bare_app` is True when Typer makes `var`'s only command the app itself (see `_is_bare_command_app`), so that
    command's recipe runs the app with no command token.
    """
    key = (src.module, var)
    if key in active:
        raise EndpointRecipeError(f"typer app {src.module}:{var} is added to itself; a group cannot contain its parent")
    active = active | {key}

    candidates: list[tuple[ast.FunctionDef, str | None, bool]] = [
        (func, src.command_name(func, var), False) for func in src.functions
    ]
    candidates += [
        (func, _registered_command_name(call, func, src.file), True) for func, call in src.bound_commands_for(var)
    ]
    for func, command, bound in candidates:
        if command is None:
            continue
        where = f"{src.file}:{func.lineno} {func.name}"
        exposed = src.is_exposed(func)
        if exposed:
            for decorator in src.exposed_decorators(func):
                read_exposed_arguments(decorator, where, src.literal_dicts)
        if not any(part == "cli" or part.endswith("_cli") for part in src.module.split(".")):
            raise EndpointRecipeError(
                f"{where}: command {command!r} lives in {src.module}; put every entrypoint under <package>.cli"
            )
        params = _recipe_params(
            _without_self(func) if bound else func,
            where,
            command,
            lambda param, name: sources.option_alias(src, name, param, where),
        )
        if _is_destructive(command) and not any(p.name == "confirm" and p.default is None for p in params):
            raise EndpointRecipeError(
                f"{where}: command {command!r} changes state, so it needs a required --confirm option"
            )
        prefix = config.prefix_for(src.module)
        found.append(
            EndpointRecipe(
                name=config.recipe_name(src.module, command),
                prefix=prefix,
                command=command,
                path=group_path if bare_app else (*group_path, command),
                doc=_first_doc_line(func),
                params=params,
                exposed=exposed,
            )
        )

    sources_and_vars = []
    for call in src.registrations(var):
        if not call.args:
            raise EndpointRecipeError(f"{src.file}:{call.lineno}: add_typer needs the typer app as its first argument")
        group_name = _keyword_literal(call, "name", f"{src.file}:{call.lineno} add_typer")
        child_src, child_var = sources.resolve_group(src, call.args[0])
        sources_and_vars.append((child_src, child_var, group_name))

    for child_src, child_var, group_name in sources_and_vars:
        if group_name is None:
            group_name = _typer_name(child_src, child_var)
        if group_name is None:
            nested: list[EndpointRecipe] = []
            _collect(child_src, child_var, (), sources, config, nested, active)
            if nested:
                raise EndpointRecipeError(
                    "a nested typer group with endpoints has no name; pass name= to add_typer so its commands "
                    "can be invoked"
                )
            continue
        if not isinstance(group_name, str):
            raise EndpointRecipeError(f"{src.file}: add_typer name must be a string")
        _collect(child_src, child_var, (*group_path, group_name), sources, config, found, active)


def _typer_name(src: _Source, var: str) -> str | None:
    """The name given to a Typer(...) constructor, or None."""
    call = src.typers.get(var)
    if call is None:
        return None
    name = _keyword_literal(call, "name", f"{src.file}: Typer for {var}")
    return name if isinstance(name, str) else None


def _first_doc_line(func: ast.FunctionDef) -> str:
    """The first line of a command's docstring, or a fallback."""
    text = ast.get_docstring(func) or ""
    return text.splitlines()[0] if text else "Run endpoint"


def endpoint_recipes(module: str, app_name: str, config: RecipeConfig) -> list[EndpointRecipe]:
    """Find every command of `module:app_name` and its nested groups, by reading their source.

    Every command is a recipe, so the convention is that entrypoints live under <package>.cli. The decorator
    `@expose_api_secure` marks a command for an API route as well; it does not decide whether a recipe exists.
    Each recipe is `<prefix>-<command-name>`, where the prefix is the module's override or the default and the
    command name is the leaf name.

    Raises:
        EndpointRecipeError: If the source cannot be read as a typer app, an endpoint argument is not a literal,
            or two endpoints would generate the same recipe name or share a command name.
    """
    sources = _Sources()
    top = sources.load(module, resolve_module_file(module))
    if top.app_typer(app_name) is None:
        raise EndpointRecipeError(f"{module}:{app_name} is not a typer.Typer assigned at module level")

    found: list[EndpointRecipe] = []
    _collect(top, app_name, (), sources, config, found, frozenset(), _is_bare_command_app(top, app_name))
    # A leaf command name used by two commands (for example `standard check` and `typer-explicit check`) cannot name
    # both recipes, so each clashing recipe takes its prefix and full command path. Renaming a command would break
    # every caller of its CLI path, so the path is the disambiguator instead.
    leaf_counts = Counter(recipe.command for recipe in found)
    for index, recipe in enumerate(found):
        if leaf_counts[recipe.command] > 1 and recipe.path:
            if recipe.command in config.names:
                raise EndpointRecipeError(
                    f"command {recipe.command!r} clashes with another command of the same name, so [names] cannot "
                    "give it one recipe name; remove its [names] entry, which then uses the path"
                )
            found[index] = replace(recipe, name=f"{recipe.prefix}-{'-'.join(recipe.path)}")
    found.sort(key=lambda r: (r.name, r.command))
    endpoint_commands = {recipe.command for recipe in found}
    stray = sorted(set(config.names) - endpoint_commands)
    if stray:
        raise EndpointRecipeError(
            f"[names] in recipes.toml names {stray}, which match no endpoint command; "
            "check the spelling (the command name is the leaf name, with '-' for '_')"
        )
    seen_names: dict[str, str] = {}
    for recipe in found:
        if recipe.name in seen_names:
            raise EndpointRecipeError(
                f"endpoints {seen_names[recipe.name]!r} and {recipe.command!r} would both generate "
                f"{recipe.name!r}; rename one command or give its module a different prefix in [modules]"
            )
        seen_names[recipe.name] = recipe.command

    by_path: dict[tuple[str, ...], EndpointRecipe] = {}
    for recipe in found:
        key = (*recipe.path, recipe.command)
        first = by_path.setdefault(key, recipe)
        if first is not recipe:
            raise EndpointRecipeError(f"endpoint command {' '.join(key)!r} is defined twice; rename one")
    return found
