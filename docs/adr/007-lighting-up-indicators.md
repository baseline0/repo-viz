<!-- agentic-id: ADR_RV_007_LIGHTING_UP -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-007: Lighting up coupling, hotspot and SATD

## Decision

Three literature-backed slots from ADR-006 become enabled: `coupling`, `hotspot` and `satd`. `coverage` and `code_health` stay disabled because no producer is supplied. Thresholds are derived from repo-viz's own snapshot and documented as context-specific priors: coupling p90=3/p95=5 → partial 2, violation 4; corrected churn x coupling p90=6/p95=10/max=30 → partial 6, violation 12.

SATD values come from a tokenize-based comment scan (`TODO|FIXME|HACK|XXX|BUG`) invoked by `just indicators ... REPO=<path>`; string literals never count. Symbols inherit their enclosing file's path, so file-level producers and churn apply to methods and classes. No value means `na`, never a pass.

## Consequences

- The viewer shows real signals immediately for a repo-viz snapshot; a different repo should re-derive thresholds.
- Hotspot no longer evaluates to zero when churn lives on files and fan-out lives on symbols.
- Adding another producer requires one function in `producers.py` and a `values` key, not renderer changes.

## Specification Map

- `src/repo_viz/indicators/producers.py` — `satd_from_source`, `satd_counts`.
- `src/repo_viz/indicators/builtin.py` — `_node_path`, `_churn_for`, corrected `hotspot`.
- `src/repo_viz/cli.py`, `justfile` — `--repo` producer hook.
- `config/indicators.toml` — enabled flags and derived thresholds.
