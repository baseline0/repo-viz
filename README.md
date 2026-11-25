# repo-viz

Interactive membrane visualizer for a repository: nested containers, semantic zoom, data/control/security tracks, and a status strip on each membrane wall. This repository currently provides the static analysis pipeline that produces the versioned graph artifact; the Svelte canvas viewer and agentic audit/dispatch surface follow in later phases.

Analysis is static-only: the snapshot records hierarchy, imports, calls, inheritance, ingress/egress signatures, complexity and git churn. Coverage is deliberately absent until an on-demand audit runs.

## Development

    uv sync --dev
    just test
    just check
    just analyze /home/mark/projects/tool-core --out graph.json
    just summary graph.json

Snapshots are derived artifacts: regenerate them with `just analyze`, never edit them by hand.
