# GUI Overview (PySide6)

This document inventories the current GUI surface area and maps each action to the underlying core or CLI implementation. The CLI and tests remain the source of truth for behavior and schemas.

## Tabs and Views

### Overview
- **Purpose:** Read-only summary of the current `Engine` object with a compact context header, primary dyno shortcut, and grouped subsystem cards for quick review.
- **Backing:** `gui/main_window.py::update_overview`.
- **Status:** Supported.

### Properties
- **Purpose:** Edit component values (Block, Head, Camshaft, Intake, Exhaust, SimulationSettings, and related subsystems).
- **Backing:** `gui/main_window.py` property editor bindings using `Engine` dataclasses.
- **Status:** Supported.

### Guided Engine Creation
- **Purpose:** Create a valid engine preset without manual JSON editing.
- **Levels:** `Basic`, `Advanced`, `Expert`.
- **Flow:** collect use-case, architecture, aspiration, target RPM window, and objective, then build a coherent preset through `core.engine_wizard`.
- **Status:** Supported. Generated presets are preflight-validated before they can be applied.

| Level | User inputs | What the wizard generates |
|---|---|---|
| Basic | use-case, architecture, aspiration, target RPM window, objective | full base preset with guided geometry, valvetrain, efficiency, and boost defaults |
| Advanced | Basic + displacement, compression ratio, runner length, header length | same base preset, but with mid-level sizing overrides applied |
| Expert | Advanced + diameters, peak/redline rpm, thermal/flow efficiency, cam specs, ignition, target boost | full preset with direct control over the exposed top-level calibration inputs |

| Wizard output | Notes |
|---|---|
| `Engine` preset | built in `core.engine_wizard`, not in GUI-only code |
| engineering summary | bore/stroke, displacement per cylinder, RPM target, geometry, valvetrain, boost, efficiency, piston speed |
| optional JSON export | saves a normal backward-compatible engine preset |
| preflight review | split into blockers and warnings before apply/export |

### Quick Dyno
- **Purpose:** Run power and torque sweep and plot results.
- **Mode v1 (Quick 0D):** `core.thermo.CylinderSimulator`.
- **Mode v2 (Pro Coupled):** `core.pro_dyno_v2.ProDynoV2Runner`.
- **Status:** Supported.
- **Layout:** A compact run-context card sits above `Run Settings` and `Run Actions`, with `Result Summary` expanded into a wider status/metrics block below so the primary run flow reads with less compression in normal window sizes.
- **Cross-mode note:** `ve_actual` remains visible in both modes, but the GUI now states explicitly that it is a modeled VE estimate in v1 and a trapped-mass result in v2, so cross-mode reads are trend/plausibility checks rather than strict parity checks.
- **Result summary:** Quick Dyno now surfaces peak power, peak torque, the RPM for both peaks, and the active sweep range directly in the tab without changing solver behavior or export payloads.
- **Run-state polish:** Idle `Cancel` stays out of the primary flow, advanced dyno controls remain collapsed/optional by default, and the plot now carries a short caption with project/engine/run context for quick traceability.
- **Chart cleanup:** Invalid point markers remain visible on the plot when present, but they are no longer promoted into the main legend alongside the normal power/torque series.
- **Export note:** Dyno JSON exports now repeat that caveat in `observable_semantics.ve_actual`.

### Analysis
- **Purpose:** Tabular breakdown of v1 dyno results.
- **Backing:** `gui/main_window.py::update_analysis_table`.
- **Status:** v1-only.

### Real Dyno
- **Purpose:** Import measured dyno data, preview the canonical dataset package, compare simulator vs real data, and run staged assisted calibration.
- **Backing:** `gui.real_dyno_workbench.RealDynoWorkbench`.
- **Core reuse:** `pywavedyn.dyno_data.import_dyno_file`, `pywavedyn.dyno_data.write_dataset_package`, `pywavedyn.bench.evaluate_with_engine`, `pywavedyn.staged_calibration.run_staged_calibration`, `pywavedyn.engineering_diagnostics`.
- **Status:** Supported in GUI as an orchestration layer over the backend/CLI logic.

| GUI step | What the user does | Backend source of truth |
|---|---|---|
| Import source | choose CSV/JSON source and output dataset folder | `pywavedyn.dyno_data.write_dataset_package` |
| Explicit mapping | assign `rpm`, `torque`, `power`, and optional channels | `pywavedyn.dyno_data.import_dyno_file` |
| Unit normalization | review or override source units | `pywavedyn.dyno_data._convert_value` via importer |
| Reuse last import | reopen the import dialog with the last mapping, units, notes, and output folder prefilled | GUI session state only; canonical import still runs in backend |
| Canonical preview | inspect normalized `target_curve.json` content and import warnings | canonical dataset package |
| Adaptive mode selection | leave combustion adaptive mode as configured or force it on/off for the session | `pywavedyn.combustion_mode.apply_adaptive_combustion_mode` |
| Compare | run simulation vs dataset on selected/current engine | `pywavedyn.bench.evaluate_with_engine` |
| Staged calibration | run airflow/friction/combustion stages and report omitted stages | `pywavedyn.staged_calibration.run_staged_calibration` |
| Feature validation | compare baseline vs adaptive/turbo toggles and staged-after on the loaded dataset | `pywavedyn.validation_compare.run_validation_batch` |
| A/B compare | compare two explicit modes on the same dataset | `pywavedyn.ab_sensitivity.run_ab_compare` |
| Local sensitivity | rank a small set of stable parameters by signal influence | `pywavedyn.ab_sensitivity.run_local_sensitivity` |
| Optimize-guided view | run dataset-error guided search on the loaded dataset | `core.optimize_runner.optimize_guided` |
| Export | write compare report or staged artifacts | GUI writes backend-produced JSON payloads |

| What the GUI shows | Meaning |
|---|---|
| import warning | source data was imported, but something should be reviewed |
| compare skipped signal | dataset had a signal that the current simulator path could not score |
| diagnostic | evidence-backed interpretation derived from the current report, not a hidden heuristic |
| `accepted` stage | official staged-calibration status when the filtered calibration objective improved and the stage was applied |
| `rejected` stage | official staged-calibration status when the candidate did not improve the filtered objective |
| `omitted` stage | official staged-calibration status when signals are missing or no physically-supported parameter exists yet |
| validation outcome | official comparison outcome: `improved`, `partial_improvement`, `tradeoff`, `no_clear_benefit`, or `no_conclusion` from backend comparison logic |
| local robustness | official local robustness level: `low_sensitivity`, `moderate_sensitivity`, or `high_sensitivity` for the tested local perturbation only |

Additional analysis tabs inside `Real Dyno`:

| Tab | What it visualizes | What not to infer |
|---|---|---|
| Compare | overlay of real vs simulated torque/power, signal coverage, optional-signal metrics, diagnostics | not a proof of root cause by itself |
| Calibration | per-stage accepted/rejected/omitted status plus before/after overlays | not a guarantee of contract closure |
| Validation | baseline vs feature-on summaries across adaptive/turbo/staged-after | not a global verdict for every engine or dataset |
| A/B | explicit A vs B signal deltas and overlay curves | not a causal explanation beyond scored signals |
| Sensitivity | local influence ranking by signal and tradeoff flags | not full uncertainty quantification |
| Optimize | ranked candidates, best candidate, score, tradeoffs, and locality warnings | not a proof of global optimality |

Workflow polish now present in `Real Dyno`:
- last dataset path is remembered and can be reloaded quickly
- last import mapping/units are reused to reduce repetitive CSV/JSON setup
- long actions show a busy state and temporarily disable conflicting buttons
- available reports can be exported as a bundle or reopened later for visual inspection
- bundle export now adds a minimal `manifest.json` index so available artifacts can be located without changing the individual report payloads
- migrated analysis reports now prefer an additive top-level common envelope with `report_type`, `report_format_version`, `report_family`, `generated_at_utc`, and `context`
- report loading prefers `report_type` when present and still falls back to legacy shape heuristics for older artifacts

Turbo/thermal note for Real Dyno:
- the GUI reuses backend turbo staging when boost evidence and supported turbo controls exist;
- thermal remains visible only as a limitation/omitted stage unless the backend gains a stronger comparable thermal signal path.

### Pro Dyno
- **Purpose:** Run v2 coupled sweep with convergence plots.
- **Backing:** `core.pro_dyno_v2.ProDynoV2Runner`.
- **Status:** Supported.

### Wave Sim
- **Purpose:** Exhaust wave scope visualization and audio capture.
- **Backing:** `core.simulator.Engine1DSolver`, `core.wave_utils`, `acoustics.audio_generator`.
- **Status:** Supported.

### Fabrication
- **Purpose:** Heuristic fabrication table and cut-list report.
- **Backing:** `gui/main_window.py`.
- **Status:** Prototype UI convenience.

## File and Project Actions
- **File -> New Guided Engine...:** launch the three-level wizard and optionally export the generated preset to JSON.
- **File -> Load/Save:** `Engine.from_dict` and `Engine.save_to_file`.
- **Export Dyno JSON:** writes CLI-compatible dyno output validated against `schemas/dyno.schema.json`.
- **Real Dyno tab -> Import dyno data...:** writes a canonical dataset package without duplicating CLI parsing logic.

## Validation
- GUI execution paths reuse shared core validation; the GUI does not duplicate physical rules.
- Dyno, Pro Dyno, wave scope, and optimization sweep now run a shared preflight validator before execution.
- Existing JSON presets continue to load through `Engine.from_dict` and preserve backward compatibility.

| Preflight rule family | Current coverage | Outcome |
|---|---|---|
| displacement range | yes | blocks |
| firing order count and uniqueness | yes | blocks |
| compression ratio outside recommended range | yes | warns |
| absurd redline | yes | blocks |
| cam peak rpm far from redline | yes | warns |
| intake/exhaust geometry outside recommended range | yes | warns |
| turbo enabled with missing target boost/PR | yes | blocks |
| turbo map absence / bad intercooler efficiency | yes | blocks |
| conflicting boost systems | yes | blocks |
| missing minimum fields for dyno/scope/full-scope | yes | blocks |
| v2-specific gas and seat-diameter requirements | yes | blocks |

| Not covered in this version | Notes |
|---|---|
| detailed combustion stability heuristics | out of scope for this pass |
| advanced acoustic suitability scoring | out of scope for this pass |
| geometry manufacturability beyond coarse ranges | still handled as engineering review, not hard validation |

## Notes
- GUI features must reuse core runners; no simulator defaults are changed by the GUI.
- When a configuration option is not exposed in the GUI, it is preserved on load/save and can be edited in JSON or via CLI.
- The Real Dyno flow does not invent turbo or thermal calibration behavior. Those stages are shown as omitted until the backend exposes physically-supported parameters.
