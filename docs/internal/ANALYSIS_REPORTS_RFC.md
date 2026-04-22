# Analysis Reports RFC

## Status
- Phase 1 only.
- Design/RFC document, not a migration.
- No current report schema or payload shape changes are implied by this file.

## Objective
Define a short, reviewable path toward a common contract for analysis artifacts produced by the backend/CLI and consumed by the GUI or bundle export flows.

This RFC is intended to reduce:
- shape-based report detection in the GUI
- duplicated context fields with different names
- repeated outcome/label semantics across report families
- drift between standalone reports and bundle metadata

## Audited Artifacts
The following current artifacts were reviewed for this RFC:

| Artifact | Backend source | Current schema/source of shape |
|---|---|---|
| compare / bench report | `pywavedyn/bench.py` | `schemas/bench_report.schema.json` |
| staged calibration | `pywavedyn/staged_calibration.py` + CLI wrapper | `schemas/staged_calibration.schema.json` |
| validation compare | `pywavedyn/validation_compare.py` + CLI wrapper | `schemas/validation_compare.schema.json` |
| A/B compare | `pywavedyn/ab_sensitivity.py` + CLI wrapper | `schemas/ab_compare.schema.json` |
| sensitivity local | `pywavedyn/ab_sensitivity.py` + CLI wrapper | `schemas/sensitivity_local.schema.json` |
| optimize guided | `core.optimize_runner` + CLI wrapper | `schemas/optimize_guided.schema.json` |
| analysis bundle manifest | `pywavedyn/analysis_bundle.py` | no schema; helper contract only |

## Current Findings

### Common fields already present
- Most report families already carry useful execution metadata such as `version`.
- `compare`, `staged_calibration`, and `optimize_guided` already use a similar `metadata` shape with `input_hash`, `timestamp`, `version`, `settings`, and `coupling_mode`.
- Most analysis reports already carry some dataset context, usually including `dataset_id`, `engine_id`, and `preset_path`.
- `compare`, `validation_compare`, and `ab_compare` already expose some form of `signal_coverage`.
- `compare` and `staged_calibration` already expose `diagnostics`.
- `validation_compare` and `ab_compare` already expose explicit `outcome` values and human-readable `note` text.
- The bundle `manifest.json` now provides a minimal external index with `artifact_type`, `filename`, and basic dataset context when available.

### Same concept, different field names
- Timestamp/version:
  - report metadata uses `metadata.timestamp`
  - bundle manifest uses `generated_at_utc`
  - manifest also uses `bundle_version`, not report-level version
- Engine/preset path context:
  - `compare.dataset.preset_path`
  - `staged_calibration.preset_base_path`
  - `validation_compare.metadata.base_engine_path`
  - `sensitivity_local.metadata.engine_path`
  - `ab_compare.metadata.engine_a_path` / `engine_b_path`
- Dataset path context:
  - `compare.dataset.path`
  - `validation_compare.metadata.datasets_evaluated`
  - nested `cases[].dataset.path`
- Signal coverage naming:
  - `compare.signal_coverage.compared_signals`
  - `validation_compare.case.signal_coverage.compared_signals`
  - `ab_compare.signal_coverage.compared_signals_union`
- Outcome-like status naming:
  - `validation_compare.features[*].outcome`
  - `ab_compare.comparison.outcome`
  - `staged_calibration.stages[*].accepted` plus note-driven `omitted` semantics in GUI
  - `sensitivity_local.params[*].tradeoff_detected` and robustness labels, but no top-level outcome

### Repeated outcome or label semantics
- `validation_compare.py` defines `OUTCOME_ORDER = improved, partial_improvement, tradeoff, no_clear_benefit, no_conclusion`.
- `ab_compare` uses the same outcome vocabulary via shared comparison helpers.
- `gui/real_dyno_workbench.py::_outcome_badge` repeats display mapping for those outcomes.
- `staged_calibration` uses `accepted/rejected/omitted` semantics that are closely related but not yet normalized into the same vocabulary.

### Common useful context that should be easy to standardize later
- `dataset_id`
- `engine_id`
- `preset_path`
- engine source path or base engine path
- report generation time/version
- report family/type
- signal coverage summary

### GUI dependencies on shape heuristics today
`gui/real_dyno_workbench.py::_load_report_payload` currently identifies report families by key combinations:
- optimize guided: `optimization_problem` + `best_candidate` + `candidates`
- A/B compare: `comparison` + `signal_coverage` + `dataset`
- sensitivity local: `params` + `summary` + `baseline`
- validation compare: `cases` + `summary` + `metadata`
- staged calibration: `stages` + `final_params`
- compare: `errors` + `points` + `dataset`

This works today, but it is fragile for additive growth because:
- unrelated future fields can make families look more alike
- the GUI has to know report internals instead of relying on an explicit type marker
- bundle manifest helps locate files, but it does not solve standalone artifact detection

## Compatibility Principles
- Backend/CLI remain the source of truth for artifact semantics.
- Future contract changes must be additive at first.
- Existing top-level payload shapes must remain readable by current tests and consumers during transition.
- Legacy artifacts without the future common fields must continue to open in the GUI.
- New fields should help identify and contextualize a report, not wrap or rewrite existing report-specific content in Phase 2 or 3.

## Proposed Future Common Envelope
This RFC proposes a future common envelope added at top level, alongside current fields, not instead of them.

Proposed future common fields:
- `report_type`
- `report_format_version`
- `report_family`
- `generated_at_utc`
- `context`

Proposed meanings:
- `report_type`: explicit stable identifier such as `compare_report`, `staged_calibration_report`, `validation_compare_report`, `ab_compare_report`, `sensitivity_local_report`, `optimize_guided_report`
- `report_format_version`: version of the common report contract, independent from git/build version
- `report_family`: initial value `analysis`
- `generated_at_utc`: normalized generation timestamp for the common contract
- `context`: common lightweight context object

Proposed `context` minimum:
- `dataset_id`
- `engine_id`
- `preset_path`
- `engine_path` or `base_engine_path` when relevant

Important non-goal for the future envelope:
- do not move existing report-specific payload under a new nested `payload` object in the first migration wave

That would create a breaking shape change and would not meet the current compatibility policy.

## Legacy + New Read Strategy
When the common contract is introduced in a later phase:
1. Writers should add the common top-level fields without removing existing fields.
2. Readers should prefer `report_type` when present.
3. Readers should fall back to current shape heuristics when `report_type` is absent.
4. Tests should explicitly cover both legacy and typed artifacts for a transition period.

This strategy keeps:
- old standalone JSON artifacts readable
- new bundle exports explicit
- GUI migration incremental instead of all-at-once

## Recommended First Wave
The first reports that should gain the future common fields are:
1. compare / bench report
2. staged calibration
3. validation compare
4. A/B compare
5. sensitivity local
6. optimize guided

Reason:
- they are the artifacts already handled together by the Real Dyno workflow
- they already share enough context to benefit from explicit typing
- they are the shapes currently detected by GUI heuristics

The bundle manifest should stay a bundle index, not become a substitute for per-report type markers.

## What Should Not Be Done Yet
- Do not wrap current report payloads under a new nested envelope.
- Do not rename current fields just to make them consistent.
- Do not centralize outcome enums in this phase.
- Do not change production schemas in this phase.
- Do not mix this work with threading, worker services, or bundle UX redesign.
- Do not claim semantic identity between v1 and v2 observables where the code/docs already treat them as comparable-but-not-identical.

## Compatibility Map

| Current artifact | Current explicit type field | Current context fields | Current status/outcome fields | Current GUI detection | Future common additions |
|---|---|---|---|---|---|
| compare / bench report | none | `dataset.dataset_id`, `dataset.engine_id`, `dataset.preset_path`, `dataset.path` | `contract.pass` | `errors` + `points` + `dataset` | `report_type=compare_report`, common `context`, normalized `generated_at_utc` |
| staged calibration | none | `preset_base_path`, `dataset`, artifact paths | `stages[].accepted`, note-driven omitted/rejected semantics | `stages` + `final_params` | `report_type=staged_calibration_report`, common `context`, explicit stage-status normalization later |
| validation compare | none | `metadata.base_engine_path`, `metadata.datasets_evaluated`, `cases[].dataset.*` | `baseline/features[*].outcome`, summary counts | `cases` + `summary` + `metadata` | `report_type=validation_compare_report`, common `context` per case and/or top level |
| A/B compare | none | `dataset.*`, `metadata.engine_a_path`, `metadata.engine_b_path` | `comparison.outcome` | `comparison` + `signal_coverage` + `dataset` | `report_type=ab_compare_report`, common `context`, explicit variant context kept separate |
| sensitivity local | none | `dataset.*`, `metadata.engine_path` | `params[*].tradeoff_detected`, robustness labels | `params` + `summary` + `baseline` | `report_type=sensitivity_local_report`, common `context` |
| optimize guided | none | report-specific optimization payload, often target-derived context but not standardized | candidate feasibility/warnings, not shared outcome vocabulary | `optimization_problem` + `best_candidate` + `candidates` | `report_type=optimize_guided_report`, common `context` when dataset-backed |
| bundle manifest | `artifact_type` per entry only | entry `context.dataset_id/engine_id/preset_path` when available | none | external bundle index only | keep as bundle index; do not treat as replacement for per-report type marker |

## Phase Boundaries
- Phase 1: this RFC and compatibility map only
- Phase 2: centralize repeated outcomes/labels
- Phase 3: add common top-level envelope fields to selected reports and update schemas additively
- Later: reduce GUI shape heuristics once typed reports are broadly available

## Decision Summary
- Create a new internal RFC document now.
- Keep it short and implementation-facing.
- Prefer additive top-level common fields later rather than a new wrapping payload.
- Preserve legacy reads by keeping shape heuristics as fallback until migration is complete.
