# repo-viz

Interactive membrane visualizer for a repository: nested containers, semantic zoom, data/control/security tracks, and a status strip on each membrane wall. The static analysis pipeline produces a versioned graph artifact; the Svelte + Canvas 2D viewer renders it with frozen circle-packing layout, an offscreen color-picking buffer and LOD culling. Agentic audit/dispatch follows in Phase 4.

Analysis is static-only: the snapshot records hierarchy, imports, calls, inheritance, ingress/egress signatures, complexity and git churn. Coverage is deliberately absent until an on-demand audit runs.

## Development

    uv sync --dev
    just test
    just check
    just analyze /home/mark/projects/tool-core --out graph.json
    just summary graph.json
    just frontend-check
    just check-indicators
    just indicators graph.json indicators.json
    just serve graph.json --indicators indicators.json

Membrane slots are generic: `config/indicators.toml` binds a glyph, palette position, trigger and context-specific thresholds to a dotted Python evaluator. Set `enabled = false` for an indicator whose producer is not configured for a repo (coverage, coupling, hotspot, SATD and code-health proxy are off by default — see ADR-006). Evaluators read producer values from `EvaluationContext.values` and never fabricate a result: absent data yields `na`. Coupling, hotspot and SATD are enabled (ADR-007); pass `REPO=<checkout>` to `just indicators` to run the SATD producer before evaluation, e.g. `just indicators graph.json indicators.json render /home/mark/projects/repo-viz`. Run with `change` to evaluate after a refactor.

`just serve` builds the viewer into `src/repo_viz/static/` (git-ignored) and serves `/graph.json`, `/config.json`, `/indicators.json`, `/healthz` and `/readyz` on port 8080. The viewer accepts `?graph=<url>` to load a different snapshot.

Snapshots and indicator results are derived artifacts: regenerate them, never edit them by hand.
