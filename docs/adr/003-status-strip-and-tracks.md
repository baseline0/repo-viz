<!-- agentic-id: ADR_RV_003_STATUS_STRIP -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-003: Polarized status strip and three visualization tracks

## Decision

Each membrane reserves a fixed right-hand arc of at most 90 degrees (`315deg` to `45deg`) for five permanent slots in fixed order: security/trust, boundary integrity, efficiency/complexity, hygiene, antipattern sentinel. States are `verified` (teal), `na` (slate), `partial` (amber) or `violation` (crimson). Two display modes are supported: full spectrum (all slots) and calm membrane (only degraded slots protrude).

Dependency ports are distributed over the remaining 290 degrees, so receptor and egress glyphs never collide with the status strip. At macro zoom the strip collapses to a segmented arc; at meso it expands to socketed glyphs; at micro the parent strip fades as children display their own strips on the same compass arc.

Three tracks are independent toggles. Data carries HTTP/DB/event weight, control carries call/import/inheritance, security carries ingress receptors and egress sinks. Egress and secret sources are identified by explicit dotted-prefix signature tables in `classify.py`; tags bubble up to the parent membrane halo.

## Consequences

- Absence of an antipattern is visible as a verified slot, not as blank space.
- Slot meaning is positional, so a scan does not require reading labels.
- New sinks or frameworks require one table entry, not parser changes.

## Specification Map

- `src/repo_viz/model.py` — `StatusSlot`, `StatusState`, `StatusStrip`, `RESERVED_ARC`.
- `src/repo_viz/status.py` — `status_for`, `rollup_status`.
- `src/repo_viz/classify.py` — `EGRESS_SIGNATURES`, `SECRET_SOURCES`, `INGRESS_DECORATORS`.
