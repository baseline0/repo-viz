"""Structured CLI output: commands build data, this module decides how to print it.

## Specification Map

- ``JsonOption`` — the single ``--json`` flag shared by every command.
- ``CommandOutput`` — accumulates human lines and a JSON-serializable data object.
- ``command_output`` — prints either the lines or exactly one JSON object.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import typer

JsonOption = typer.Option(False, "--json", help="Emit one JSON object instead of human text")


@dataclass
class CommandOutput:
    """The result of one command, independent of how it is rendered."""

    json_output: bool
    lines: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def echo(self, message: str) -> None:
        """Record a human-readable line."""
        self.lines.append(message)


@contextmanager
def command_output(json_output: bool) -> Iterator[CommandOutput]:
    """Render accumulated output when the command body finishes."""
    out = CommandOutput(json_output=json_output)
    yield out
    if json_output:
        typer.echo(json.dumps(out.data, indent=2, sort_keys=True))
        return
    for line in out.lines:
        typer.echo(line)
