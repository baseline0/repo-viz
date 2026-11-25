<!-- agentic-id: ADR_RV_005_GENERIC_INDICATOR_SLOTS -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-005: Generic indicator slots with pluggable evaluators

## Decision

The membrane status strip is no longer a fixed five-metric taxonomy. An indicator slot is a configuration entry pairing a visual descriptor (glyph, color, compass position) with a dotted Python callable that quantifies or qualifies one aspect of a component on demand. `config/indicators.toml` declares the slots, which are enabled, which triggers run them (`render`, `change`) and their budgets. Evaluators are pure functions over `(node, context)`, return a state/value/evidence triple, and are resolved with `importlib`. Disabled or unevaluable indicators render as `na`, never as a false pass.

## Consequences

- Coverage is an optional indicator, not a built-in assumption about every repo.
- New indicators require one config entry plus one function, not renderer changes.
- Results are a separate derived artifact, evaluated at snapshot render time or after a change, so the static graph stays immutable.
- The legacy `status` field on nodes remains in `graph@1` for compatibility; the viewer prefers configured indicator results.

## Specification Map

- `src/repo_viz/indicators/` — config spec, loader, registry, evaluator protocol, built-ins.
- `config/indicators.toml` — declarative slot scheme.
- `frontend/src/` — config-driven slot rendering and result panel.
