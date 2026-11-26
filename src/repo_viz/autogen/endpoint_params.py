"""Turn a command's typer options into recipe parameters, with their defaults."""

from __future__ import annotations

import ast
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from repo_viz.autogen.endpoint_source import _decorator_name, _is_typer_call
from repo_viz.autogen.recipe_config import EndpointRecipeError

FlagMode = Literal["value", "presence", "pair"]


@dataclass(frozen=True)
class RecipeParam:
    """A typer option passed through to a recipe parameter.

    `default` is the option's literal default as text (rendered as a just string default), or None when the option is
    required and the recipe takes no default for it. `mode` says how the recipe passes the value: `value` passes it
    after `flag`, `presence` emits `flag` only for true, and `pair` emits the true or false side of a Typer dual flag.
    """

    name: str
    flag: str
    default: str | None = None
    mode: FlagMode = "value"


def _is_ellipsis(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is Ellipsis


def _is_bool_annotation(node: ast.expr | None) -> bool:
    """True for `bool` and `Annotated[bool, ...]`, the forms a Typer flag option uses."""
    if isinstance(node, ast.Name):
        return node.id == "bool"
    if (
        isinstance(node, ast.Subscript)
        and _decorator_name(node.value) == "Annotated"
        and isinstance(node.slice, ast.Tuple)
        and node.slice.elts
    ):
        return _is_bool_annotation(node.slice.elts[0])
    return False


def _typer_spec(arg: ast.arg, default: ast.expr | None) -> ast.Call | None:
    """The typer.Option/Argument call that declares `arg`, from its Annotated metadata or its default."""
    annotation = arg.annotation
    if (
        isinstance(annotation, ast.Subscript)
        and _decorator_name(annotation.value) == "Annotated"
        and isinstance(annotation.slice, ast.Tuple)
    ):
        for element in annotation.slice.elts[1:]:
            if _is_typer_call(element) and isinstance(element, ast.Call):
                return element
    if _is_typer_call(default) and isinstance(default, ast.Call):
        return default
    return None


_ELLIPSIS_NODE = ast.Constant(value=Ellipsis)


def _typer_default(call: ast.Call) -> ast.expr | None:
    """The default a typer.Option/Argument call declares: its first positional, or `default=`. None when absent."""
    if call.args:
        return call.args[0]
    return next((keyword.value for keyword in call.keywords if keyword.arg == "default"), None)


def _recipe_default(arg: ast.arg, node: ast.expr, where: str) -> str | None:
    """The recipe default for an option's literal default `node`, or None when the option gets no parameter.

    A bool is a flag and keeps its old behaviour (no parameter). None means "no value" and is also left out. Any
    other literal must be a str, int, or float, since the recipe passes it as one string.
    Raises:
        EndpointRecipeError: If the default is not a literal, or is a literal the recipe cannot pass as one value.
    """
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError):
        raise EndpointRecipeError(
            f"{where}: parameter {arg.arg!r} has default {ast.unparse(node)}, which is not a literal. The generator "
            "reads option defaults from source without running the module, so write a literal (a string, int, or "
            "float) as the default"
        ) from None
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        if "\n" in value or "\r" in value:
            raise EndpointRecipeError(f"{where}: parameter {arg.arg!r} default {ast.unparse(node)} spans lines")
        return value
    if isinstance(value, int | float):
        return str(value)
    raise EndpointRecipeError(
        f"{where}: parameter {arg.arg!r} has default {ast.unparse(node)}, a {type(value).__name__}; a recipe "
        "parameter takes one string, so give the option a str, int, or float default"
    )


def _alias_default_refusal(command: str, param: str, annotation: str, default: str, where: str) -> EndpointRecipeError:
    """The refusal for an option alias that also has a signature default, which the generator cannot combine."""
    return EndpointRecipeError(
        f"{where}: command {command!r} parameter {param!r} uses option alias {annotation!r} and also has the signature "
        f"default {default}. An alias and a signature default cannot be combined, so the generator refuses it rather "
        f"than drop the parameter. Fix it by removing the default from the signature and putting it in the alias, "
        f"Annotated[T, typer.Option({default}, ...)], or by declaring the option inline in the signature with its "
        f"default, Annotated[T, typer.Option({default}, ...)]"
    )


def _recipe_params(
    func: ast.FunctionDef, where: str, command: str, resolve_alias: Callable[[str, str], ast.Call]
) -> tuple[RecipeParam, ...]:
    """Options of a command that become recipe parameters, in declaration order.

    A required parameter whose annotation names an option alias (`repo: TargetRepo`, with `TargetRepo =
    Annotated[str, typer.Option(...)]`) takes its option from `resolve_alias(param, annotation_name)`, which reads the
    alias by ast and refuses one it cannot resolve.

    - An option with no default (`...`) is required: the recipe takes it with no default.
    - An option with a literal default (str, int, or float) is a recipe argument with that default.
    - A bool option with a default is a flag and stays out of the recipe, as before. A required bool option becomes a
      true/false recipe parameter, rendered as a flag or as the side of a Typer dual flag.
    - A typer.Argument with a default is not a recipe parameter, as before.
    - An option alias with a signature default (`repo: RepoOption = "x"`) is refused: the default cannot be combined
      with the alias, and dropping it silently would leave the recipe without the parameter.
    Raises:
        EndpointRecipeError: If a required parameter is positional (repos declare options as --name value, and a
            recipe that dropped a positional would run the command without it), if an alias is combined with a
            signature default, or if a default is not a literal or cannot be passed as one string.
    """
    positional = [*func.args.posonlyargs, *func.args.args]
    defaults: list[ast.expr | None] = [None] * (len(positional) - len(func.args.defaults)) + list(func.args.defaults)
    keyword_only = list(func.args.kwonlyargs)
    keyword_defaults: list[ast.expr | None] = list(func.args.kw_defaults)

    params: list[RecipeParam] = []
    for arg, default in [*zip(positional, defaults, strict=True), *zip(keyword_only, keyword_defaults, strict=True)]:
        if arg.annotation is not None and _decorator_name(arg.annotation) == "Context":
            continue  # typer.Context is not a click parameter
        spec = _typer_spec(arg, default)
        alias = False
        if spec is None and default is None:
            if arg.annotation is None:
                raise EndpointRecipeError(
                    f"{where}: parameter {arg.arg!r} is a required positional argument; "
                    "declare it as typer.Option(..., '--name') and pass --name value"
                )
            spec = resolve_alias(arg.arg, ast.unparse(arg.annotation))  # refuses what it cannot read
            alias = True
        if spec is None and default is not None and isinstance(arg.annotation, ast.Name):
            # A signature default on a plain name: an option alias here would be dropped silently, so refuse it. A
            # name the generator cannot read as an alias is an ordinary parameter, and stays out as before.
            try:
                resolve_alias(arg.arg, arg.annotation.id)
            except EndpointRecipeError:
                pass
            else:
                raise _alias_default_refusal(command, arg.arg, arg.annotation.id, ast.unparse(default), where)
        if spec is None:
            continue
        if default is None:
            # An inline Annotated declaration with no signature default stays required. An alias reads its own default.
            declared = _typer_default(spec) if alias else None
            value: ast.expr | None = declared if declared is not None else _ELLIPSIS_NODE
        elif _is_typer_call(default) and isinstance(default, ast.Call):
            value = _typer_default(default)  # `= typer.Option(...)`: the declaration carries the default
        else:
            value = default  # a plain default, or an Annotated declaration overridden by a signature default
        if value is None:
            continue  # typer.Option() with no default: optional, no value
        is_argument = _decorator_name(spec) == "Argument"
        if _is_ellipsis(value):
            if is_argument:
                raise EndpointRecipeError(
                    f"{where}: parameter {arg.arg!r} is a required positional argument; "
                    "declare it as typer.Option(..., '--name') and pass --name value"
                )
            recipe_default = None
        elif is_argument:
            continue  # an optional positional is not passed through, as before
        else:
            recipe_default = _recipe_default(arg, value, where)
            if recipe_default is None:
                continue  # a flag or a None default: optional, as before
        flags = [node.value for node in spec.args if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        flags = [flag for flag in flags if flag.startswith("-")]
        flag = max(flags, key=len) if flags else "--" + arg.arg.replace("_", "-")
        mode: FlagMode = "pair" if "/" in flag else "presence" if _is_bool_annotation(arg.annotation) else "value"
        params.append(RecipeParam(name=arg.arg, flag=flag, default=recipe_default, mode=mode))
    return tuple(params)
