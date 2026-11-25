<!-- agentic-id: ADR_RV_004_SVELTE_CANVAS -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-004: Svelte + Canvas 2D build-step exception

## Decision

repo-viz builds a Svelte + TypeScript frontend with Vite, despite fleet-ops ADR-006 choosing HTMX with no build step. That decision is repo-local to fleet-ops; repo-viz needs an offscreen color-picking buffer, semantic-zoom culling and pre-rasterized status sprites, which SVG/HTMX fragments cannot provide at interactive frame rates. The built assets are git-ignored and served as static files, so the Python package remains the deployable artifact.

## Consequences

- Node/npm are needed only to build; the served artifact is static HTML/JS.
- `just frontend-build` writes to `src/repo_viz/static/` (git-ignored via `frontend/dist/` plus explicit ignore).
- The service blueprint (FastAPI mount at `/`, probes, port 8080) remains the Phase 5 target; Phase 3 uses a stdlib static server with `/healthz` and `/readyz`.
- No frontend Node version is pinned, matching the rest of the fleet.

## Specification Map

- `frontend/src/` — layout, renderer, picking buffer, sprites, Svelte app.
- `justfile` — `frontend-install`, `frontend-check`, `frontend-build`, `serve`.
- `src/repo_viz/web.py` — static server and probes.
