<!-- agentic-id: ADR_RV_010_MCP_SURFACE -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-010: MCP surface with read-only default

## Decision

repo-viz exposes MCP through `MCPServer` from `mcp>=2.2.0,<3`, matching the fleet's `tool-*` pattern. Four read tools (`get_summary`, `get_indicator_results`, `get_indicator_config`, `check_indicator_config`) are always registered; two file-writing tools (`analyze`, `collect`) are registered only when the server is started with `--allow-write` (or `REPO_VIZ_ALLOW_WRITE`). Tool results use the fleet envelope (`ok`, `data` / `error`) and never expose human-only operations.

Streamable HTTP is mounted at `/mcp` on the FastAPI service alongside `/api/v1/collect`, and stdio is available through the `repo-viz-mcp` console script. The existing constant-time auth middleware now covers `/mcp` as well as `/api/*`; probes remain public. `tool.manifest.json` declares transport, endpoint, port 8080 and `read_only_by_default: true`.

## Consequences

- Agents can inspect snapshots and indicator results without mutation by default; collection requires an explicit opt-in.
- The gateway names tools as `repo-viz.<tool>`; write tools also require a write capability in the caller's role.
- Registration in `fleet-coordination` and a policy in `fleet-toolbox` are separate, reviewed changes.

## Specification Map

- `src/repo_viz/mcp_server.py` — tool registry, envelope, stdio entry point.
- `src/repo_viz/server.py` — Streamable HTTP routes and `/mcp` authentication.
- `tool.manifest.json`, `tests/unit/test_mcp_server.py`, `tests/integration/test_api.py` — contract and tests.
