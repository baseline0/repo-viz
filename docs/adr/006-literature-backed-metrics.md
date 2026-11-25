<!-- agentic-id: ADR_RV_006_LITERATURE_METRICS -->
<!-- doc-class: advisory -->
<!-- lifecycle: specify -->
<!-- authority: canonical -->

# ADR-006: Literature-backed metric selection

## Evidence source

`tool-lit-review` searched arXiv `cs.SE` since 2020 (192 candidates, 146 relevant); 13 open-licence PDFs were fetched, extracted and embedded with `tool-rag` into a scratch LanceDB. `assess` supplied surface interest signals; `rag_search`/`rag_ask` supplied efficacy claims with title citations. Assessment scores are *not* quality judgments, and the fetched manifest carries no DOI, so citations use title and arXiv id.

## Shortlist

| Metric | Interest | Efficacy evidence | Decision |
|---|---|---|---|
| CodeHealth / smells | 10 papers mention smells; top assess scores | Paired experiment, 24,620 solutions; break-even CH 4.9 (C++)–7.1 (Python); authors warn CH optimization ≠ maintainability gain (2610.33343) | Add `code_health` as producer-backed proxy, disabled |
| Hotspots / change coupling | churn in 8 papers, hotspots in 5 | Industrial multi-case study uses code health, hotspots and change coupling for maintenance prioritization, aligned with perceived pain (2607.01850) | Add `hotspot` = churn x coupling, disabled |
| Structural coupling / design metrics | structural metrics in 9 papers | Architectural-degradation review: structural design metrics in 92.3% of primary studies (2610.01611) | Add `coupling`, disabled |
| SATD markers | debt in 10 papers | Empirical study: >60% of SATD covered by tests; co-change and impact matter (2609.13485) | Add `satd` as producer-backed count, disabled |
| Coverage | 9 papers | No universal efficacy threshold in this corpus | Keep existing disabled slot |
| Energy impact | strong methodology, 2.50 assess | Measures runtime energy, not maintainability decisions (2608.06620) | Not added |

## Threshold policy

"Making Software Metrics Useful" (2603.16012) reports that metrics rarely answer decisions such as *should I refactor this class?*; the threshold-setting paper argues for context-specific thresholds. Therefore every new slot ships `enabled = false` with configurable `thresholds` in `config/indicators.toml`; values from the literature are priors only, not defaults imposed on every repo. Pomona's 82.1% merge rate for small agentic PRs (2606.06752) supports incremental dispatch rather than wholesale refactoring.

## Specification Map

- `config/indicators.toml` — new disabled slots and per-slot thresholds.
- `src/repo_viz/indicators/builtin.py` — `coupling`, `hotspot`, `satd`, `code_health`; context threshold overrides.
- `src/repo_viz/indicators/spec.py` — `Indicator.thresholds`, `EvaluationContext.values`.
