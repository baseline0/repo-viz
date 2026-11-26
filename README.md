# repo-viz

Interactive membrane visualizer for a repository: nested containers, semantic zoom, data/control/security tracks, and a status strip on each membrane wall. The static analysis pipeline produces a versioned graph artifact; the Svelte + Canvas 2D viewer renders it with frozen circle-packing layout, an offscreen color-picking buffer and LOD culling. Agent-driven read and collection are available through the FastAPI service and MCP surface; audit/dispatch work-item flows are the remaining piece.

Analysis is static-only: the snapshot records hierarchy, imports, calls, inheritance, ingress/egress signatures, complexity and git churn. Coverage remains disabled until a producer supplies real coverage data.

## Development

    uv sync --dev
    just test
    just check
    just rv-analyze /home/mark/projects/tool-core --out graph.json
    just rv-summary graph.json
    just frontend-check
    just rv-check-indicators
    just rv-evaluate-indicators graph.json --out indicators.json --repo /home/mark/projects/repo-viz
    just rv-serve graph.json

The `rv-*` recipes are generated from the Typer app in `src/repo_viz/cli.py`; regenerate them with `just generate-endpoints` and verify with `just check-endpoints`.

Membrane slots are generic: `config/indicators.toml` binds a glyph, palette position, trigger and context-specific thresholds to a dotted Python evaluator. Set `enabled = false` for an indicator whose producer is not configured for a repo (churn and code-health proxy are off by default — see ADR-006). Evaluators read producer values from `EvaluationContext.values` and never fabricate a result: absent data yields `na`. Security, boundary, complexity, hygiene, sentinel, coupling, hotspot, SATD, architectural drift, cognitive friction and co-change are enabled; pass `--repo <checkout>` to `just rv-evaluate-indicators` to run the SATD and co-change producers before evaluation. Run with `change` to evaluate after a refactor.

`just rv-serve` builds the viewer into `src/repo_viz/static/` (git-ignored) and serves `/graph.json`, `/config.json`, `/indicators.json`, `/healthz` and `/readyz` on port 8080. `just rv-api` starts the authenticated FastAPI service with `/api/v1/collect` and Streamable HTTP MCP at `/mcp` for agent-driven collection. The viewer accepts `?graph=<url>` to load a different snapshot.

MCP exposes four read tools (`get_summary`, `get_indicator_results`, `get_indicator_config`, `check_indicator_config`) by default; `analyze` and `collect` are registered only with `--allow-write` (or `REPO_VIZ_ALLOW_WRITE`). The stdio entry point is `repo-viz-mcp`; see ADR-010.

Snapshots and indicator results are derived artifacts: regenerate them, never edit them by hand.

`arch_drift`, `cognitive_friction` and `cochange` are enabled with thresholds derived from repo-viz's own graph; their evidence tiers and citations are in ADR-008. `--repo` supplies the SATD and co-change producers, and `--coverage` can supply a pytest-cov JSON file for the coverage slot.

See `CONTRIBUTING.md` for setup, test tiers (`tests/unit/`, `tests/integration/`, shared fixtures in `tests/conftest.py`), and the branch/commit workflow.
