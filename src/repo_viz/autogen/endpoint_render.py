"""Render endpoint recipes as just text."""

from __future__ import annotations

from repo_viz.autogen.endpoint_discovery import EndpointRecipe
from repo_viz.autogen.endpoint_params import RecipeParam


def _just_string(text: str) -> str:
    """`text` as a double-quoted just string literal."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _flag_choice(param: RecipeParam, true: str, false: str) -> str:
    """A just conditional that emits `true` or `false` for a boolean recipe parameter."""
    return (
        "{{ if "
        + param.name
        + ' == "true" { '
        + _just_string(true)
        + " } else if "
        + param.name
        + ' == "false" { '
        + _just_string(false)
        + " } else { error("
        + _just_string(param.name + " must be true or false")
        + ") } }}"
    )


def _render_arg(param: RecipeParam) -> str:
    """Render one parameter as CLI arguments, choosing the flag for boolean parameters."""
    ref = "{{ " + param.name + " }}"
    if param.mode == "value":
        return f'{param.flag} "{ref}"'
    if param.mode == "presence":
        return _flag_choice(param, param.flag, "")
    true_flag, false_flag = param.flag.split("/", 1)
    return _flag_choice(param, true_flag, false_flag)


def _render_endpoint(recipe: EndpointRecipe, invocation: str) -> str:
    """Render one endpoint recipe, passing its options through as recipe parameters.

    just needs parameters with a default to come after those without, so required parameters are listed first, each
    group in declaration order. The command line keeps declaration order.
    """
    ordered = sorted(recipe.params, key=lambda p: p.default is not None)
    declared = [p.name if p.default is None else f"{p.name}={_just_string(p.default)}" for p in ordered]
    header = f"{recipe.name} {' '.join(declared)}".rstrip()
    args = " ".join(_render_arg(p) for p in recipe.params)
    words = [invocation, *recipe.path, args]
    body = "    " + " ".join(word for word in words if word)
    return f'# {recipe.doc}\n[group("{recipe.prefix}")]\n{header}:\n{body}'
