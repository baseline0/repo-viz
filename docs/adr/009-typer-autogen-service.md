<!-- agentic-id: ADR_RV_009_TYPER_AUTOGEN_SERVICE -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-009: Typer as SSoT via copied autogen, with an authenticated API

## Decision

The Typer app in `src/repo_viz/cli.py` is the single source of truth for both human recipes and agent-facing HTTP routes. The canonical generators from `fleet_base` are **copied and adapted** into `src/repo_viz/autogen/` (AST recipe generator, FastAPI route generator, exposure decorator, two-name constants shim) rather than imported. Reason: repo-viz's registered charter requires `allowed_fleet_dependencies: []`, so importing fleet-base would be an architectural violation. Copying keeps the paved-road semantics and drift guards without a fleet dependency; the original modules remain the design authority and are cited in the copied package docstring.

Generated artifacts are tracked: `just/generated.just` (`rv-*` recipes) and `src/repo_viz/api_routes_autogen.py`. `just check-endpoints` and `just gen-check` fail when they drift; hand-written recipes for CLI commands were removed.

The service uses FastAPI with constant-time `FLEET_API_KEY` / `FLEET_API_KEYS(_FILE)` middleware, public probes (`/healthz`, `/readyz`, deprecated `/ready`), generated `/api/v1/collect`, and the static viewer mounted last. Routes are generated as *unsecured* (`@expose`) so emitted code has zero fleet imports; authorization is centralized in middleware instead of per-route `AccessChecker`. `tool.manifest.json` declares probes and entry points but no MCP surface yet.

## Consequences

- Adding or changing a CLI command requires regenerating both artifacts; `gen-check` is a gate.
- Required CLI arguments had to become `--name` options, and option defaults had to become string/int literals, because the AST generator reads source without importing it.
- API callers use `POST /api/v1/collect` with `{repo, out_dir, trigger, days}`; the handler calls the same `collect_metrics` function as the CLI.
- A future MCP surface should be added deliberately, with a registry entry; none exists today.

## Specification Map

- `src/repo_viz/autogen/` — copied generators, exposure decorator, wrapper CLI.
- `src/repo_viz/server.py`, `auth.py`, `operations.py` — service, auth, shared orchestration.
- `just/generated.just`, `src/repo_viz/api_routes_autogen.py` — generated artifacts.
