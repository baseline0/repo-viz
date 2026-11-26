<!-- agentic-id: ADR_RV_011_AUDIT_WORK_ITEM -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-011: Audit reports and human-authorized work-item requests

## Decision

Clicking a component no longer leaves the viewer inert. `audit` builds a deterministic `repo-viz/audit@1` report from an existing snapshot and indicator results: degraded indicators become findings with severity, evidence and a suggested action. `prepare-work-item` turns that report into a self-contained request artifact (`work-item.json` and a canonical-shape `work-item.yaml`).

repo-viz does **not** create or dispatch fleet work items. There is no MCP creation/dispatch tool in the fleet, and `repo-viz` is not in fleet-ops' `DISPATCH_ALLOWED_REPOSITORIES`. The emitted request therefore has `status: idea`, null `gate`/`gate_repo`/`gate_hash`, and explicit evidence locators. An operator translates it into `fleet-ops work-item create ...` or places it in the canonical queue and sets `status: authorized` after supplying owner-pinned gate data.

The viewer calls dev-only POST routes on the local static server; the authenticated FastAPI service exposes generated `/api/v1/audit` and `/api/v1/work-item` routes from the same Typer commands. Fleet-toolbox also exposes `audit_component` (read) and `prepare_work_item` (write) through the repo-viz MCP policy, so agents can complete the diagnose → propose loop through the gateway. Responses use the fleet read-envelope contract.

## Consequences

- No fleet package is imported, preserving the registered charter (`allowed_fleet_dependencies: []`).
- Dispatch cannot happen accidentally: the artifact is a proposal, not an authorized queue item.
- Agent-driven dispatch later requires an owner decision on allowlisting repo-viz and a gate pin.

## Specification Map

- `src/repo_viz/audit.py`, `src/repo_viz/workitem.py` — pure core and artifact writer.
- `src/repo_viz/cli.py`, `src/repo_viz/web.py`, `frontend/src/App.svelte` — entrypoints and viewer wiring.
- `tests/unit/test_audit.py`, `tests/integration/test_cli.py` — tests.
