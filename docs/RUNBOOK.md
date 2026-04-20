# RUNBOOK

## Installation (base)
```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

## GUI extras (PySide6)
Install PySide6 if you want the GUI or GUI tests:
```bash
python -m pip install PySide6
```

Verify the GUI starts:
```bash
python main.py
```

## Guided engine creation
The GUI now supports `File -> New Guided Engine...` with `Basic`, `Advanced`, and `Expert` flows. The wizard generates a valid preset through shared core logic, shows a summary, and can export the generated engine directly to JSON.

## Shared preflight validation
Dyno, scope, sweep, map, and full-scope CLI paths now run a shared core preflight validator before execution. The GUI uses the same preflight layer before dyno, pro dyno, scope, and optimization sweep.

| Guided level | Inputs required | Overrides allowed |
|---|---|---|
| Basic | use-case, architecture, aspiration, RPM start/end, objective | none |
| Advanced | Basic inputs | displacement, compression ratio, runner length, header length |
| Expert | Advanced inputs | runner/header diameters, peak/redline rpm, thermal efficiency, port flow efficiency, cam durations/lifts/LSA, ignition, target boost |

| Preflight outcome | Meaning |
|---|---|
| blocker | run is stopped until the issue is corrected |
| warning | run may continue, but the configuration should be reviewed |

| Covered checks | Outcome |
|---|---|
| displacement / cylinder count consistency | blocker |
| firing order integrity | blocker |
| absurd redline / missing v2 gas constants | blocker |
| turbo conflicts and missing boost targets | blocker |
| missing minimum run fields | blocker |
| recommended CR / geometry ranges | warning |
| suspicious cam peak rpm vs redline | warning |

## Validation layers
Use the validation surface as separate layers, not as interchangeable proofs:

| Layer | What it is for | What it does not prove |
|---|---|---|
| `selfcheck` | deterministic sanity checks, expectation matching, and lightweight physical invariants | external dyno fidelity |
| regression-golden benchmark | detect silent drift against versioned in-repo references | absolute physical accuracy to a real engine |
| real-data benchmark / calibration | compare and fit against imported dyno data with traceable artifacts | solver validity outside the imported scenario and signal coverage |

The current `selfcheck` output now includes explicit physical-invariant checks for pressure, temperature, VE bounds, power-vs-torque consistency, and BMEP-vs-torque consistency.

What is covered today by automated evidence:
- v1 vs v2 comparability is covered narrowly through a stable-point `ve_actual` comparison, because `ve_actual` is intentionally not the same observable in both modes.
- `outlet_mode="impedance"` has dedicated outlet-response unit coverage; it is not just a documented flag.
- physical invariants are visible through `selfcheck`, but that layer is still a compact sanity surface rather than an exhaustive conservation proof of every subsystem.
- mesh/resolution coverage is currently limited to local sensitivity smoke tests on small 1D pulse problems; it is not a formal grid-convergence certification.

## Dyno real-data import and comparison
Flexible import:
```bash
python -m pywavedyn.cli dyno-import --input curve.csv --out out_dataset --dataset-id my_run --engine-id my_run --preset-path presets/honda_k20.json --format csv --mapping rpm=speed_rpm,power_hp=hp_col,torque_nm=tq_col,map_kpa=map_abs --units power_hp=hp,torque_nm=lbft,map_kpa=kpa_abs
```

GUI import:
- Open the `Real Dyno` tab.
- Choose the base engine to compare against: current editor engine or a separate engine JSON.
- Click `Import dyno data...`.
- Select the source CSV/JSON.
- Confirm explicit field mapping and source units.
- Choose the output dataset package directory.
- On later imports, the dialog reuses the last mapping, units, notes, and output folder as a starting point.
- Review the canonical preview and any import warnings before comparing.

Current committed real-data package status:
- `benchmarks/datasets/k20_like_real/` and `benchmarks/datasets/v8_like_real/` are the canonical committed `real_data` packages in the repo today. They use `metadata.json`, `target_curve.json`, committed `source.csv`, and `source_sha256` traceability.
- `benchmarks/datasets/f1_like_real/` remains a documented placeholder legacy dataset with header-only `targets.csv`; do not treat `f1_like_real` as a canonical committed real-data package.
- In this repo state, the committed canonical real-data packages remain torque/power-only evidence cases. Turbo, fueling, and thermal channels are supported by the import/compare contract, but they are not yet committed as stronger real-data evidence in `k20_like_real` or `v8_like_real`.

Compare simulator vs imported dyno:
```bash
python -m pywavedyn.cli dyno-compare --engine presets/honda_k20.json --dataset out_dataset --adaptive-combustion as_is --out compare.json
```

Comparative validation across cases:
```bash
python -m pywavedyn.cli validate-features --engine presets/honda_k20.json --datasets out_dataset benchmarks/datasets/k20_like_real --out validation_compare.json --with-adaptive-toggle --with-staged-calibration
```

This report compares the supplied baseline against feature variants already implemented in the product:
- adaptive combustion `on/off`
- turbo incremental `on/off` when the engine is actually turbocharged
- staged calibration `before/after`

Interpret the per-feature outcome as the official comparison vocabulary shared by backend, GUI, and docs:
- `improved`: scored signals improved without new regressions
- `partial_improvement`: some scored signals improved, but the gain is incomplete
- `tradeoff`: one group of scored signals improved while another worsened
- `no_clear_benefit`: no useful gain appeared on the scored signals
- `no_conclusion`: the currently available signals were not enough to support a claim

Use `signal_evidence` to read that limitation honestly:
- `contract_baseline` covers the torque/power contract signals
- `turbo` covers `boost_kpa` / `map_kpa`
- `fueling` covers `lambda` / `afr`
- `thermal` covers `egt_c`
- a group may be `compared`, `present_not_compared`, or `not_available`

Direct A/B comparison:
```bash
python -m pywavedyn.cli compare-ab --engine-a presets/honda_k20.json --engine-b presets/honda_k20.json --dataset out_dataset --label-a baseline --label-b adaptive_on --adaptive-combustion-b on --out ab_compare.json
```

Local sensitivity and basic robustness:
```bash
python -m pywavedyn.cli sensitivity-local --engine presets/honda_k20.json --dataset out_dataset --params ve_scale,friction_scale,burn_scale --out sensitivity_local.json
```

Current sensitivity scope is intentionally local and limited to stable exposed knobs:
- `ve_scale`
- `friction_scale`
- `burn_scale`
- `adaptive_duration_scale`
- `adaptive_ca50_offset_deg`
- `turbo_target_boost_scale`
- `turbo_spool_rpm_offset`

Interpretation guidance:
- `rankings_by_signal` shows which parameter produced the largest local change on each scored signal
- `robustness_by_signal` classifies the local response using the official local robustness levels `low_sensitivity`, `moderate_sensitivity`, or `high_sensitivity`
- `tradeoff_detected` means a local perturbation helped one scored signal while hurting another
- this is not full uncertainty quantification, not a confidence interval, and not a global claim outside the tested neighborhood

## Guided optimization
Use `optimize-guided` when you want a bounded, interpretable search instead of a single legacy runner-length sweep.

Example against a real-data target:
```bash
python -m pywavedyn.cli optimize-guided --engine presets/honda_k20.json --objective dataset_error --params burn_scale,friction_scale --target out_dataset --max-signal-mape power_hp=0.3,torque_nm=0.3 --max-evals 12 --out optimize_guided.json
```

Example for dyno-style objective without a target dataset:
```bash
python -m pywavedyn.cli optimize-guided --engine presets/legacy/custom_twin_230cc.json --objective peak_power --params intake.runner_length --rpm-grid 2500,3500,4500,5500 --param-bounds intake.runner_length=0.20:0.60 --max-evals 10 --out optimize_guided.json
```

Current supported parameter set:
- `intake.runner_length`
- `ve_scale`
- `friction_scale`
- `burn_scale`
- `adaptive_duration_scale`
- `adaptive_ca50_offset_deg`
- `turbo_target_boost_scale`
- `turbo_spool_rpm_offset`

Current supported objectives:
- `dataset_error`
- `peak_power`
- `mean_torque_band`
- `boost_target_tracking`

Current guardrails:
- `max_signal_mape`
- `min_peak_power_hp`
- `min_mean_torque_nm`

How to read the report:
- `optimization_problem` defines the exact objective, params, bounds, and constraints
- `baseline` is the starting configuration
- `candidates` are the top tried candidates kept for traceability
- `best_candidate` is the best feasible candidate if one exists; otherwise the best overall candidate is reported with a warning
- `tradeoff_notes` flags when the best dataset-fit candidate improved one scored signal but worsened another
- `fragility` warns when top scores are extremely close, meaning the result should be treated as local and potentially brittle

What it does not mean:
- it is not a generic optimizer over all engine parameters
- it does not prove a global optimum
- it should not be used yet for poorly conditioned geometry, thermal, or solver-internal knobs

GUI compare:
- Click `Compare simulation vs real`.
- Read torque/power MAPE, contract pass/fail, dataset signals, compared signals, and skipped signals.
- Review the diagnostics section for evidence-backed engineering observations and the signals used to support them.
- Use the overlay plot to inspect real vs simulated torque and power curves.

Run staged assisted calibration:
```bash
python -m pywavedyn.cli calibrate-staged --engine presets/honda_k20.json --dataset out_dataset --adaptive-combustion on --out staged_calibration.json --max-evals-per-stage 10
```

GUI staged calibration:
- Click `Run staged calibration`.
- Review the stage table:
  - official staged-calibration statuses:
  - `accepted`: stage improved the filtered objective and was applied.
  - `rejected`: candidate did not improve the filtered objective.
  - `omitted`: missing signals or no supported parameter exists for that stage.
- Review the diagnostics section for omitted stages, partial improvements, and adaptive-combustion outcomes.
- Use `Export calibration artifacts...` to save `staged_calibration.json`, `calibrated_engine.json`, `benchmark_before.json`, and `benchmark_after.json`.

GUI advanced result views in `Real Dyno`:
- `Validation` tab:
  - runs the same `validate-features` logic over the loaded dataset
  - shows baseline vs adaptive/turbo/staged-after outcomes as `improved`, `partial_improvement`, `tradeoff`, `no_clear_benefit`, or `no_conclusion`
  - use it to see what helped on scored signals, not to claim global accuracy
- `A/B` tab:
  - compares two explicit modes such as baseline vs adaptive-on
  - shows per-signal MAPE deltas and overlay curves for torque/power
  - a worsened signal stays visible; the GUI does not hide regressions
- `Sensitivity` tab:
  - runs the same local perturbation backend used by `sensitivity-local`
  - shows ranking by signal, local robustness label, and parameter-level tradeoff flags
  - treat this as local behavior around the current setup, not uncertainty quantification
- `Optimize` tab:
  - runs dataset-error `optimize-guided` on the loaded dataset
  - shows the best candidate, top candidates, score, constraints, tradeoff notes, and locality warnings
  - this remains a bounded local/grid search, not a claim of global optimum

General UX notes for `Real Dyno`:
- buttons that would conflict with an active compare/calibration/validation run are temporarily disabled while the current action is running
- the workbench keeps a recent dataset path so you can use `Reload last dataset`
- `Open analysis report...` lets you inspect a previously saved compare/validation/A-B/sensitivity/optimize report without rerunning the backend
- `Export analysis bundle...` writes the currently available JSON artifacts together so the session stays traceable
- the bundle now includes a minimal `manifest.json` index listing only the artifacts actually written, with artifact type, filename, and basic dataset context when available

Outputs:
- `metadata.json` stores mapping, original units, signals present, import warnings, and source traceability.
- `metadata.json` also stores additive `signal_evidence` so the dataset package itself says which optional real channels are actually committed.
- `target_curve.json` stores canonical signals in normalized units.
- `compare.json` keeps the benchmark contract on torque/power and adds optional-signal metrics when available.
- `compare.json`, `validation_compare.json`, `ab_compare.json`, `sensitivity_local.json`, and `staged_calibration.json` now carry additive `signal_evidence` summaries so missing real-channel evidence is explicit instead of implied.
- `staged_calibration.json` stores per-stage before/after metrics, accepted/rejected decisions, and skipped-stage reasons.
- compare and staged-calibration reports also record whether adaptive combustion was left `as_is` or forced `on/off`.
- `diagnostics` arrays in dyno/compare/staged reports store structured findings with severity, confidence, signals used, rationale, and suggested interpretation.
- `validation_compare.json` is the comparative validation layer. It does not prove global accuracy; it only reports what changed on the signals actually scored for each case.
- migrated analysis artifacts now also add the same top-level common envelope fields: `report_type`, `report_format_version`, `report_family`, `generated_at_utc`, and `context`.
- the envelope is additive only; historical fields stay in place and the GUI still falls back to legacy shape detection when opening older artifacts.
- `manifest.json` is a bundle index only; it does not change the shape of any individual analysis artifact JSON.

## Turbo response model (opt-in)
The current turbo path remains steady-state by default. An additional opt-in response layer can now delay achieved boost relative to commanded PR using only existing turbo-side signals:

```json
{
  "turbo": {
    "enabled": true,
    "target_boost_kpa": 60.0,
    "response_model": {
      "enabled": true,
      "spool_rpm": 3200.0,
      "spool_width_rpm": 800.0,
      "flow_ref_kg_s": 0.12,
      "flow_width_kg_s": 0.04,
      "min_response": 0.25
    }
  }
}
```

What it uses:
- engine `rpm`
- estimated air mass flow through the current turbo operating point
- the commanded compressor PR after target/wastegate logic

What it changes:
- achieved `pr_comp`
- resulting `boost_kpa`
- charge temperature and therefore downstream combustion/load interaction

What staged calibration may tune in this iteration:
- `turbo_target_boost_scale`
- `turbo_spool_rpm_offset`

Turbo-stage guardrails:
- the stage runs only if the engine is turbocharged
- the stage needs boost evidence in the dataset (`boost_kpa` and/or `map_kpa`)
- if no supported turbo control is exposed, the stage is reported as `omitted`

Thermal status in this iteration:
- `wall_thermal` remains a coarse trend/stability model
- no new thermal calibration stage is claimed because the current compare path still lacks a strong, directly comparable thermal signal such as predicted EGT

Initial diagnostics implemented:

| Diagnostic | Signals used | Meaning | Limit |
|---|---|---|---|
| compare contract fail | torque, power | main fit still fails the report contract | does not explain root cause by itself |
| possible airflow shortfall | MAP + torque + power | simulated airflow side appears biased low relative to measured load/performance | suggests intake/VE shortfall, not a confirmed hardware restriction |
| boost under/overprediction | boost | simulated boost channel materially differs from measured boost | does not by itself localize the turbo root cause |
| lambda/AFR mismatch | lambda or AFR | fueling-related channel differs materially from dataset | depends on correct stoich/sensor conventions |
| skipped optional signals | coverage | some channels were present in the dataset but not scoreable | no claim is made for skipped channels |
| stage omitted/rejected | staged report | the calibration stage was not run or did not improve the filtered objective | not a solver bug by itself |
| partial staged improvement | staged before/after | calibration reduced error but still missed contract | indicates progress, not closure |
| adaptive combustion helped/disabled | adaptive stage state | adaptive stage either contributed or was unavailable | does not prove universal benefit on other datasets |
| knock penalty active | dyno | one or more RPM points are knock-limited | only reflects the current knock model/inputs |
| boost late / below configured target | dyno boost trace | boost buildup or achieved peak is below expectation | requires boost channel or configured target |

## Interpreting `ve_actual`
- In v1 / Quick Dyno, `ve_actual` is a modeled VE estimate derived from the 0D intake-flow correlations.
- In v2 / Advanced Physics Core, `ve_actual` is derived from trapped fresh mass at IVC in the coupled solution.
- They are comparable as engineering indicators, but they are not strictly identical observables. A mismatch does not by itself indicate a solver bug.
- Current automated comparison intentionally uses a stable-point plausibility band for `ve_actual`; the project does not currently claim broad v1↔v2 parity bands for torque/power across arbitrary operating points.
- The GUI now repeats this distinction directly in the dyno mode area so users do not read cross-mode VE as a direct parity target.
- CLI/GUI dyno-style exports that include `ve_actual` now also add `observable_semantics.ve_actual` so the same caveat stays attached to the artifact.

## Numba path parity
- The 1D Numba path is covered by one-step parity tests and a small multi-step parity check against the Python path.
- Current expectation is practical parity for the exercised local cases, not a promise of bit-identical behavior for every future solver extension or every runtime environment.

## Fuel configuration scope
- Alternative `afr_stoich` and `lhv_j_per_kg` values are configurable and now have small sanity coverage in the fuel-accounting path.
- This does not mean the project has full external validation for non-gasoline combustion. Today the strongest support is for accounting-level trend changes, not calibrated multi-fuel combustion fidelity.

## Flow reversal / hysteresis
- Phase-2 flow-direction logic uses stagnation totals when available, with a small hysteresis band to avoid chatter and a static fallback near equality.
- The current suite covers direction choice, backflow totals usage, ghost inversion, and choke/subsonic transitions through focused unit tests.
- This is control logic for stable nozzle-direction decisions, not a claim of experimentally validated valve hysteresis.

## Adaptive combustion mode
The 0D combustion model now has an explicit opt-in mode for condition-sensitive scheduling:

```json
{
  "combustion": {
    "adaptive_model": {
      "enabled": true,
      "duration_rpm_per_krpm": 1.5,
      "duration_load_per_bar": -0.6,
      "duration_lambda_per_lambda": 10.0,
      "ca50_load_per_bar": -0.2,
      "ca50_residual_per_frac": 10.0
    }
  }
}
```

What it uses today:
- `rpm`
- load proxy from estimated BMEP before combustion
- compression ratio
- manifold boost / intake pressure when available
- configured lambda relative to fuel stoich
- overlap-based residual proxy
- charge temperature after boost / intercooling model

What it does:
- adjusts effective burn duration
- adjusts CA50 target
- keeps the same Wiebe burn-shape framework
- records the applied signals and deltas under `trace.adaptive_combustion`
- can be forced on/off per run with `--adaptive-combustion as_is|on|off` for `dyno`, `benchmark`, `dyno-compare`, and `calibrate-staged`
- can be calibrated conservatively in staged calibration only through `adaptive_duration_scale` and `adaptive_ca50_offset_deg`

What it does not do:
- it does not infer turbulence, knock-limited MBT, or detailed in-cylinder chemistry
- it does not override explicit `combustion.wiebe` schedule overrides
- it does not change legacy behavior unless `adaptive_model.enabled=true`
- if adaptive combustion is disabled, the dedicated staged-calibration step is reported as `omitted` instead of inventing a placeholder adjustment

## Junction and thermal limits
- Intake/exhaust plenums and junction capacitance use 0D control-volume approximations. They conserve bulk quantities but do not reproduce full spatially resolved 1D mixing structure at the node itself.
- `wall_thermal` is a coarse lumped model for trend and stability work. It should not be read as a validated phase-resolved pulsating-flow heat-transfer correlation envelope.
- The current thermal evidence is trend/sanity oriented (`constant` and Dittus-Boelter variants, sign/clamp behavior, and selected EGT-direction checks), not a broad experimental validity envelope for strongly pulsating flow.
- A long-horizon lumped-wall sanity test now checks that the standalone wall model stays finite and bounded in a simple constant-gas-temperature case. This is still not a substitute for a long-duration coupled thermal validation campaign.

## CLI sanity check
```bash
python -m pywavedyn.cli --help
```

## Plenum wall thermal (opt-in)
Para evitar enfriamiento irreal por A/V, se puede habilitar masa térmica de pared en plenums:

```
\"intake_plenum\": {
  \"wall_thermal\": {
    \"enabled\": true,
    \"material\": {\"rho\": 7800.0, \"cp\": 500.0},
    \"thickness_m\": 0.003,
    \"h_model\": \"dittus_boelter\"
  }
}
```

## Species transport (opt-in)
Para activar el transporte conservativo de `Y_fresh` en 1D:

```json
{
  \"simulation_settings\": {
    \"species\": {
      \"enabled\": true,
      \"model\": \"y_fresh\"
    }
  }
}
```

## Knock report (opt-in)
Requiere `combustion.residual_coupling.enabled=true` y genera un reporte separado:

```bash
python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 2000 --mode v2 --knock-report knock.json --out dyno.json
```

## Legacy compatibility mode (opt-in)
Para presets legacy, habilitar perfil v1:

```bash
python -m pywavedyn.cli dyno --engine presets/legacy/custom_twin_230cc.json --rpm 2000 --auto-legacy-compat --out dyno.json
```

O explícito:

```bash
python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 2000 --legacy-compat v1 --out dyno.json
```

Policy:
- advanced flags stay opt-in unless explicitly enabled;
- legacy-compatible behavior should remain unchanged when those flags are absent;
- compatibility-sensitive defaults should be protected by tests, not changed silently.

## GUI smoke tests (offscreen)
Use offscreen rendering for headless CI:
```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_gui_import_smoke.py tests/test_gui_offscreen_window_smoke.py
```

## Troubleshooting Qt
- **Missing platform plugin**: set `QT_QPA_PLATFORM=offscreen` (headless) or `QT_QPA_PLATFORM=windows` (Windows desktop) before running.
- **Fonts/visual glitches**: confirm PySide6 is installed in the same Python environment as the CLI.
- **Linux headless**: ensure basic X11/wayland packages are present; use offscreen mode for tests.
