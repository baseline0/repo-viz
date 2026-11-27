# Refactor deferrals

## `wi-repoviz-repo-viz-debt` (2026-11-27)

Accepted candidates were decomposed into named, individually testable helpers:

- `generate_fastapi_from_typer` → command collection, import consolidation, prologue,
  request-model, access-check and invocation renderers.
- `_Collector` → pure class/function tag helpers; the visitor now orchestrates.
- `GraphSnapshot.from_dict` → node, edge, port and status reconstruction helpers.

Deferred candidate:

- `src/repo_viz/indicators/builtin.py::_threshold` — the reported `fan_in=18` is
  eighteen evaluators deliberately sharing one three-line threshold lookup. It is
  already the shared abstraction a wrapper would imitate; splitting it would add
  indirection without changing behavior, coupling or boundaries. Revisit only
  when threshold sources become per-indicator state rather than one context map.
