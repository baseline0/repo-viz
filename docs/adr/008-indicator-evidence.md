<!-- agentic-id: ADR_RV_008_INDICATOR_EVIDENCE -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-008: Evidence tiers for the new indicator slots

## Context

The local literature store contains 13 fetched PDFs (one of 14 manifest entries was skipped). Extraction, assessment and embedding were already complete; the store was queried again with narrow questions through Tier 3 CLI execution (`tool-lit-review rag-ask`, resident `qwen2.5-coder:7b`) because the broad synthesis question reliably returns "Insufficient local context." CLI execution follows ADR-041 in fleet-coordination; the MCP servers remain disabled in global config.

## Evidence

| Slot / concept | Claim from the store | Source | Tier |
|---|---|---|---|
| CodeHealth guidance | Paired experiment over 24,620 solutions; break-even CH 4.9 (C++) – 7.1 (Python); authors caution that optimising CH is not proof of maintainability gain | 2610.33343 | experiment (large n) |
| Architectural drift | Multivocal review of 284 studies: structural design metrics appear in 92.3% of primary studies, quality/maintainability metrics in 35.9%, degradation-specific indicators in 27.8% | 2610.01611 | survey (prevalence, not efficacy) |
| Friction / co-change | Industrial multi-case study prioritises maintenance with code health, hotspots, change coupling, refactoring-oriented views and socio-technical signals, aligned with perceived pain | 2607.01850 | case study |
| SATD | Over 60% of self-admitted debt is covered by tests; co-change and impact matter | 2609.13485 | empirical study |

The survey and case-study tiers support *relevance*, not statistical efficacy. Config entries therefore carry an `evidence` string naming the paper and tier, and the docs avoid claiming statistical validation for those slots.

## Decision

Register `arch_drift`, `cognitive_friction` and `cochange` as config slots with evidence references and context-specific thresholds. Keep them disabled until their producers are wired for a target repo; missing data renders `na`. Do not conflate the three change-related signals: `coupling` is static fan-in/out, `hotspot` is churn x coupling, and `cochange` is observed co-edit frequency from commit history.

## Specification Map

- `config/indicators.toml` — `evidence` field on each new slot.
- `src/repo_viz/indicators/spec.py` — `Indicator.evidence`, serialized to `/config.json`.
- `src/repo_viz/indicators/builtin.py` — `arch_drift`, `cognitive_friction`, `cochange`.
