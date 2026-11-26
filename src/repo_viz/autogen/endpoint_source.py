"""Read endpoint sources by ast: find typer apps, their commands and option aliases, without importing them."""

from __future__ import annotations

import ast
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from repo_viz.autogen.api_expose import EXPOSE_DECORATOR_NAMES, EXPOSED_KEYS
from repo_viz.autogen.recipe_config import EndpointRecipeError

TYPER_CALLS = frozenset({"Option", "Argument"})


def resolve_module_file(module: str) -> Path:
    """The source file of dotted `module`, found by path lookup under the working directory and sys.path.

    Raises:
        EndpointRecipeError: If no `<module>.py` or `<module>/__init__.py` exists under those roots.
    """
    parts = module.split(".")
    roots = [Path.cwd(), Path.cwd() / "src", *(Path(entry) for entry in sys.path if entry)]
    for root in roots:
        package_init = root.joinpath(*parts, "__init__.py")
        if package_init.is_file():
            return package_init
        module_file = root.joinpath(*parts[:-1], f"{parts[-1]}.py")
        if module_file.is_file():
            return module_file
    raise EndpointRecipeError(
        f"cannot find the source of module {module!r}; run from the repo root (or its src/ directory) so the "
        "module's file can be found"
    )


def _literal(node: ast.expr, where: str) -> Any:
    """The value of a literal expression, or a refusal that names `where` and the offending text."""
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError):
        raise EndpointRecipeError(
            f"{where} is {ast.unparse(node)}, which is not a literal. The generator reads @expose_api_secure "
            "arguments from source without running them, so write a literal value (a string, number, bool, or "
            "None) or, for **splat, a module-level dict literal in the same file"
        ) from None


def _keyword_literal(call: ast.Call, key: str, where: str) -> Any:
    """The literal value of keyword `key` in `call`, or None when it is absent."""
    for keyword in call.keywords:
        if keyword.arg == key:
            return _literal(keyword.value, f"{where}: {key}=")
    return None


def _decorator_name(node: ast.expr) -> str | None:
    """The bare name a decorator call is made through: `expose_api_secure` for `x.expose_api_secure(...)` too."""
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None


def read_exposed_arguments(
    decorator: ast.expr, where: str, literal_dicts: Mapping[str, dict[str, Any]]
) -> dict[str, Any]:
    """The arguments of an expose decorator, read from its source.

    Keyword and positional arguments must be literals. A `**NAME` splat is accepted only when NAME is a module-level
    dict literal in the same file. Anything else is refused.

    Raises:
        EndpointRecipeError: On a non-literal argument, an unknown key, or a missing `path`.
    """
    if not isinstance(decorator, ast.Call):
        raise EndpointRecipeError(f"{where}: @expose_api_secure must be called with arguments, at least path=")
    if len(decorator.args) > len(EXPOSED_KEYS):
        raise EndpointRecipeError(f"{where}: @expose_api_secure takes at most {len(EXPOSED_KEYS)} positional arguments")
    values: dict[str, Any] = {}
    for key, node in zip(EXPOSED_KEYS, decorator.args, strict=False):
        values[key] = _literal(node, f"{where}: {key}")
    for keyword in decorator.keywords:
        if keyword.arg is not None:
            values[keyword.arg] = _literal(keyword.value, f"{where}: {keyword.arg}=")
            continue
        splat = keyword.value
        if isinstance(splat, ast.Name) and splat.id in literal_dicts:
            values.update(literal_dicts[splat.id])
            continue
        raise EndpointRecipeError(
            f"{where}: **{ast.unparse(splat)} is not a module-level dict literal in this file; the generator "
            "cannot read it without running the module"
        )
    unknown = sorted(set(values) - set(EXPOSED_KEYS))
    if unknown:
        raise EndpointRecipeError(f"{where}: unknown @expose_api_secure argument(s) {unknown}")
    if not isinstance(values.get("path"), str):
        raise EndpointRecipeError(f"{where}: @expose_api_secure needs a literal path=")
    return values


def _is_typer_call(node: ast.expr | None) -> bool:
    """True for `typer.Option(...)` or `Option(...)` (and Argument), as written in source."""
    return isinstance(node, ast.Call) and _decorator_name(node) in TYPER_CALLS


def _alias_refusal(param: str, annotation: str, where: str, reason: str) -> EndpointRecipeError:
    """The refusal for a parameter whose annotation is an option alias the generator cannot read."""
    return EndpointRecipeError(
        f"{where}: parameter {param!r} is a required positional argument: its annotation {annotation!r} {reason}, "
        "so the generator cannot read its option. Define it at module level in this package as "
        "Annotated[T, typer.Option(...)] with literal arguments, or declare the option inline as "
        "typer.Option(..., '--name') and pass --name value"
    )


def _alias_declaration(value: ast.expr) -> ast.Call | None:
    """The typer.Option/Argument call in an `Annotated[T, typer.Option(...)]` value, or None for any other value."""
    if not (
        isinstance(value, ast.Subscript)
        and _decorator_name(value.value) == "Annotated"
        and isinstance(value.slice, ast.Tuple)
    ):
        return None
    for element in value.slice.elts[1:]:
        if isinstance(element, ast.Call) and _is_typer_call(element):
            return element
    return None


def _package_root(file: Path, module: str) -> Path:
    """The directory that holds the top-level package of `module`, given the file that defines it."""
    parts = module.split(".")
    up = len(parts) - 1 if file.name == "__init__.py" else len(parts) - 2
    root = file.parent
    for _ in range(max(up, 0)):
        root = root.parent
    return root.resolve()


class _Source:
    """One module's source, parsed with `ast`. The module itself is never imported."""

    def __init__(self, module: str, file: Path) -> None:
        self.module = module
        self.file = file
        try:
            self.tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        except SyntaxError as exc:
            raise EndpointRecipeError(f"cannot parse {file}: {exc}") from exc
        self.typers: dict[str, ast.Call | None] = {}  # the Typer(...) call, or None for a bare Typer() name
        self.factory_calls: dict[str, ast.Call] = {}  # `app = <name>()` at module level; resolved on request
        self.literal_dicts: dict[str, dict[str, Any]] = {}
        self.values: dict[str, ast.expr] = {}  # every module-level assignment's value, for option aliases
        self.imports: dict[str, tuple[str, str | None]] = {}
        self.functions: list[ast.FunctionDef] = []
        self.bound_commands: list[tuple[str, ast.FunctionDef, ast.Call]] = []  # (app var, method, its .command call)
        self._read_top_level()
        self._read_bound_commands()
        for func in self.functions:
            apps = [*self.typers, *self.factory_calls]
            if self.is_exposed(func) and not any(self.command_name(func, var) is not None for var in apps):
                raise EndpointRecipeError(
                    f"{file}:{func.lineno} {func.name} has @expose_api_secure but no @<app>.command decorator "
                    "in this module; register it as a typer command or remove the decorator"
                )

    def _read_top_level(self) -> None:
        for stmt in self.tree.body:
            if isinstance(stmt, ast.FunctionDef):
                self.functions.append(stmt)
            elif isinstance(stmt, (ast.Assign, ast.AnnAssign)) and isinstance(stmt.value, ast.expr):
                target = stmt.targets[0] if isinstance(stmt, ast.Assign) else stmt.target
                if isinstance(target, ast.Name):
                    self._read_assignment(target.id, stmt.value)
            elif isinstance(stmt, ast.ImportFrom):
                module = self._absolute(stmt)
                for alias in stmt.names:
                    self.imports[alias.asname or alias.name] = (module, alias.name)
            elif isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    if alias.asname:
                        self.imports[alias.asname] = (alias.name, None)
                    else:
                        top = alias.name.split(".")[0]
                        self.imports[top] = (top, None)

    def _read_assignment(self, name: str, value: ast.expr) -> None:
        self.values[name] = value
        if isinstance(value, ast.Call) and _decorator_name(value) == "Typer":
            self.typers[name] = value
            return
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            self.factory_calls[name] = value  # checked by app_typer only if this name is asked for as an app
            return
        try:
            literal = ast.literal_eval(value)
        except (ValueError, TypeError):
            return
        if isinstance(literal, dict):
            self.literal_dicts[name] = literal

    def app_typer(self, var: str) -> ast.Call | None:
        """The Typer(...) call behind app `var`: its own assignment, or the one its factory returns.

        Returns None when `var` is not an app assigned in this module. A `var = <name>()` whose factory cannot be
        read as a Typer(...) constructor is refused here, not at module load.
        """
        if var in self.typers:
            return self.typers[var]
        call = self.factory_calls.get(var)
        if call is None:
            return None
        self.typers[var] = self._factory_typer(var, call)
        return self.typers[var]

    def _factory_typer(self, var: str, call: ast.Call) -> ast.Call:
        """The Typer(...) a module-level `var = <factory>()` builds, read from the factory's source by ast."""
        factory = call.func.id if isinstance(call.func, ast.Name) else ast.unparse(call.func)
        where = f"{self.file}:{call.lineno} {var} = {factory}()"
        if call.args or call.keywords:
            raise EndpointRecipeError(
                f"{where} passes arguments to {factory}; the generator reads the factory without running it, so an "
                "app factory takes no arguments"
            )
        defined = [func for func in self.functions if func.name == factory]
        if not defined:
            origin = self.imports.get(factory)
            if origin is not None:
                reason = f"factory {factory} is imported from {origin[0]}, not defined in {self.module}"
            else:
                reason = f"factory {factory} is not defined in {self.module}"
            raise EndpointRecipeError(
                f"{self.module}:{var} is not a typer.Typer assigned at module level: {where} calls a factory that the "
                f"generator cannot read ({reason}). The generator reads an app factory only from the module that "
                f"assigns the app; define {factory} there, or assign its typer.Typer(...) to the name directly"
            )
        func = defined[-1]
        typer_call = _returned_typer(func)
        if typer_call is None:
            raise EndpointRecipeError(
                f"{self.file}:{func.lineno} {factory} builds {var} but does not return a Typer(...) the generator can "
                "read; end it with `return typer.Typer(...)`"
            )
        return typer_call

    def _absolute(self, stmt: ast.ImportFrom) -> str:
        """The absolute dotted name `stmt` imports from, resolving relative imports against this module."""
        if not stmt.level:
            return stmt.module or ""
        package = self.module.split(".") if self.file.name == "__init__.py" else self.module.split(".")[:-1]
        if stmt.level - 1 > len(package):
            raise EndpointRecipeError(f"{self.file}:{stmt.lineno} relative import goes above the top-level package")
        base = package[: len(package) - (stmt.level - 1)]
        return ".".join([*base, stmt.module] if stmt.module else base)

    def is_exposed(self, func: ast.FunctionDef) -> bool:
        return any(_decorator_name(dec) in EXPOSE_DECORATOR_NAMES for dec in func.decorator_list)

    def exposed_decorators(self, func: ast.FunctionDef) -> list[ast.expr]:
        return [dec for dec in func.decorator_list if _decorator_name(dec) in EXPOSE_DECORATOR_NAMES]

    def command_name(self, func: ast.FunctionDef, var: str) -> str | None:
        """The command name `@<var>.command(...)` gives `func`, or None when `func` is not registered on `var`."""
        for dec in func.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            if dec.func.attr != "command" or not (isinstance(dec.func.value, ast.Name) and dec.func.value.id == var):
                continue
            where = f"{self.file}:{func.lineno} {func.name}"
            name = _literal(dec.args[0], f"{where}: command name") if dec.args else _keyword_literal(dec, "name", where)
            if name is None:
                return func.name.replace("_", "-")
            if not isinstance(name, str):
                raise EndpointRecipeError(f"{where}: the command name must be a string")
            return name
        return None

    def registrations(self, var: str) -> list[ast.Call]:
        """The top-level `<var>.add_typer(...)` calls, each a nested group of `var`."""
        calls: list[ast.Call] = []
        for stmt in self.tree.body:
            if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)):
                continue
            call = stmt.value
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "add_typer"
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == var
            ):
                calls.append(call)
        return calls

    def _read_bound_commands(self) -> None:
        """Read `<app>.command(...)(self.<method>)` registrations in the module's classes: the commands of a CLI class.

        The receiver is the module-level app, or `self.<attr>` where the class sets `self.<attr> = <app>`. Only these two
        shapes are read; any other registration is not a command the generator knows about.
        """
        for cls in self.tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            methods = {item.name: item for item in cls.body if isinstance(item, ast.FunctionDef)}
            attr_apps: dict[str, str] = {}
            for node in ast.walk(cls):
                if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.value, ast.Name):
                    attr = _self_attr(node.targets[0])
                    if attr is not None:
                        attr_apps[attr] = node.value.id
            for node in ast.walk(cls):
                if not (isinstance(node, ast.Call) and len(node.args) == 1 and not node.keywords):
                    continue
                method = _self_attr(node.args[0])
                register = node.func
                if method is None or method not in methods:
                    continue
                if not (
                    isinstance(register, ast.Call)
                    and isinstance(register.func, ast.Attribute)
                    and register.func.attr == "command"
                ):
                    continue
                receiver = register.func.value
                if isinstance(receiver, ast.Name):
                    var = receiver.id
                else:
                    attr = _self_attr(receiver)
                    if attr is None or attr not in attr_apps:
                        continue
                    var = attr_apps[attr]
                self.bound_commands.append((var, methods[method], register))

    def bound_commands_for(self, var: str) -> list[tuple[ast.FunctionDef, ast.Call]]:
        """The class methods registered as commands of app `var`, each with its `.command(...)` call."""
        return [(func, call) for owner, func, call in self.bound_commands if owner == var]


def _self_attr(node: ast.expr) -> str | None:
    """`attr` when `node` is `self.<attr>`, else None."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
        return node.attr
    return None


class _Sources:
    """The parsed modules of one generation run, read once each."""

    def __init__(self) -> None:
        self._cache: dict[str, _Source] = {}

    def load(self, module: str, file: Path | None = None) -> _Source:
        if module not in self._cache:
            self._cache[module] = _Source(module, file if file is not None else resolve_module_file(module))
        return self._cache[module]

    def option_alias(self, src: _Source, annotation: str, param: str, where: str) -> ast.Call:
        """The typer option call that alias `annotation` stands for, read by ast from its module-level assignment.

        The alias is looked up in `src` first, then in the module it is imported from by name, when that module is in
        the same package. The module holding the alias is never imported.
        Raises:
            EndpointRecipeError: If the annotation is not a plain name that resolves to a module-level
                `Annotated[T, typer.Option(...)]`, or if its option arguments are not literals.
        """
        owner, attr = src, annotation
        if annotation not in src.values:
            imported = src.imports.get(annotation)
            if not annotation.isidentifier() or imported is None or imported[1] is None:
                raise _alias_refusal(param, annotation, where, "is not defined in this module or imported by name")
            owner = self._package_module(src, imported[0], param, annotation, where)
            attr = imported[1]
        call = _alias_declaration(owner.values[attr]) if attr in owner.values else None
        if call is None:
            raise _alias_refusal(
                param,
                annotation,
                where,
                f"is not a module-level Annotated[T, typer.Option(...)] assignment in {owner.file}",
            )
        for node in [*call.args, *(keyword.value for keyword in call.keywords)]:
            try:
                ast.literal_eval(node)
            except (ValueError, TypeError):
                raise EndpointRecipeError(
                    f"{where}: parameter {param!r} uses option alias {annotation!r}, whose option argument "
                    f"{ast.unparse(node)} is not a literal. Write the alias's arguments as literals (a string, "
                    "number, bool, or None), since the generator reads them without running the module"
                ) from None
        return call

    def _package_module(self, src: _Source, module: str, param: str, annotation: str, where: str) -> _Source:
        """The parsed module `module` that `src` imports an alias from, which must be in the same package."""
        package = src.module.split(".")[0]
        if module.split(".")[0] != package:
            raise _alias_refusal(
                param, annotation, where, f"is imported from {module}, outside the package {package!r}"
            )
        try:
            file = resolve_module_file(module)
        except EndpointRecipeError as exc:
            raise _alias_refusal(param, annotation, where, f"is imported from {module}, which has no source") from exc
        if _package_root(file, module) != _package_root(src.file, src.module):
            raise _alias_refusal(param, annotation, where, f"is imported from {module} at {file}, outside {package!r}")
        return self.load(module, file)

    def resolve_group(self, src: _Source, node: ast.expr) -> tuple[_Source, str]:
        """The module and typer variable a `add_typer` argument names, followed through imports."""
        if isinstance(node, ast.Name):
            if node.id in src.typers or node.id in src.factory_calls:
                src.app_typer(node.id)
                return src, node.id
            if node.id in src.imports and src.imports[node.id][1] is not None:
                module, attr = src.imports[node.id]
                return self.load(module), attr or node.id
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in src.imports:
            module, attr = src.imports[node.value.id]
            target = module if attr is None else f"{module}.{attr}"
            return self.load(target), node.attr
        raise EndpointRecipeError(
            f"{src.file}: cannot read {ast.unparse(node)} as a typer app; import the app as a name "
            "or as a module attribute so the generator can find its source"
        )


def _returned_typer(func: ast.FunctionDef) -> ast.Call | None:
    """The first `return Typer(...)` in `func`'s own body, skipping nested functions and classes. None when absent."""
    pending: list[ast.AST] = list(func.body)
    while pending:
        node = pending.pop(0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Call) and _decorator_name(node.value) == "Typer":
            return node.value
        pending.extend(ast.iter_child_nodes(node))
    return None
