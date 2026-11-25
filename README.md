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
    just serve graph.json

`just serve` builds the viewer into `src/repo_viz/static/` (git-ignored) and serves it with `/graph.json`, `/healthz` and `/readyz` on port 8080. The viewer accepts `?graph=<url>` to load a different snapshot.

Snapshots are derived artifacts: regenerate them with `just analyze`, never edit them by hand.
