<!-- agentic-id: ADR_RV_002_SEMANTIC_ZOOM -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-002: Semantic zoom, ancestor-chain ports and frozen layout

## Decision

Three LOD bands bind to viewport scale `k`: macro (`k<0.5`) shows opaque membranes and LCA-bubbled macro edges; meso (`0.5-2`) shows translucent membranes and perimeter ports; micro (`k>=2`) shows symbols and exact edges.

`aggregate.py` walks the full source-to-LCA-to-target ancestor chain for every leaf edge. Each wall crossed increments a port counter `(membrane, peer, direction, kind, tracks)`, so ports exist at every LOD rank without runtime routing. Port angles are assigned once by a deterministic layout step (`d3.pack` plus collision relaxation, run to completion in a synchronous worker or build step), then frozen in memory; ports use the circumference outside the reserved status arc.

The Svelte renderer uses Canvas 2D with an offscreen color-picking buffer for O(1) `getImageData` hit-testing and culls draw calls by `lod_rank` and viewport bounding-box intersection.

## Consequences

- No per-frame physics jitter and no recomputed routing paths.
- Hit-testing cost is independent of the number of visible glyphs.
- Port placement is reproducible across snapshot reloads.

## Specification Map

- `src/repo_viz/aggregate.py` — `ancestor_chain`, `lca_index`, `aggregate`.
- `src/repo_viz/model.py` — `Port`, `RESERVED_ARC`.
- `frontend/src/` (Phase 3) — frozen layout, picking buffer, LOD culling.
