<!-- agentic-id: ADR_RV_001_GRAPH_SNAPSHOT -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-001: Immutable static snapshot, on-demand audit

## Decision

`repo-viz/graph@1` is a regenerated JSON artifact containing hierarchy, leaf-derived macro edges, port counters and static metrics. The viewer only reads it. Coverage and agentic audit results are produced on demand when Mark clicks a component and are never part of the static pipeline.

## Consequences

- Rendering never waits on a test run or an agent, so zoom stays responsive.
- `coverage` is `null` in a snapshot by design; only an audit report fills it.
- Snapshots are stamped with the source commit SHA and regenerated atomically.

## Specification Map

- `src/repo_viz/model.py` — `GraphSnapshot`, `SCHEMA_VERSION`, node/edge/port invariants.
- `src/repo_viz/snapshot.py` — pure builder plus git-backed wrapper and atomic writer.
- `schemas/graph.schema.json` — external contract for the artifact.
