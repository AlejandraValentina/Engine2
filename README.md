# PyWaveDyn - Professional 1D Gas Dynamics & Engine Simulator

PyWaveDyn is a verification-focused engine simulation project with a 0D virtual dyno, a 1D gas-dynamics scope, and reproducible CLI workflows for benchmarks, selfcheck, sweeps, and reports.

## What PyWaveDyn Is
- 0D dyno for brake torque and power sweeps.
- 1D wave tooling for scope-style pressure analysis.
- CLI-first validation surface with schema-backed JSON outputs.
- GUI available, but CLI/tests are the source of truth for validated behavior.

## Install Minimum
Prerequisite: Python 3.10+

Base install:
```bash
python -m pip install -r requirements.txt
```

Optional GUI install:
```bash
python -m pip install -e ".[gui]"
```

Optional dev/test install:
```bash
python -m pip install -r requirements-dev.txt
```

## First Result
Generate a dyno JSON from the bundled K20 preset:

```bash
python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 2000:9000:250 --out out_dyno.json
```

This writes `out_dyno.json` with torque/power results in a schema-backed format.

## Validation
Public validation entry points:

```bash
python -m pywavedyn.cli benchmark --engine presets/honda_k20.json --dataset benchmarks/datasets/honda_k20_na --out bench_report.json
python -m pywavedyn.cli dyno-import --input curve.csv --out out_dataset --dataset-id my_run --engine-id my_run --preset-path presets/honda_k20.json --format csv --mapping rpm=speed,power_hp=hp,torque_nm=tq --units power_hp=hp,torque_nm=lbft
python -m pywavedyn.cli dyno-compare --engine presets/honda_k20.json --dataset out_dataset --out compare.json
python -m pywavedyn.cli calibrate-staged --engine presets/honda_k20.json --dataset out_dataset --out staged.json --max-evals-per-stage 10
python -m pywavedyn.cli validate-features --engine presets/honda_k20.json --datasets out_dataset benchmarks/datasets/k20_like_real --out validation_compare.json --with-adaptive-toggle --with-staged-calibration
python -m pywavedyn.cli compare-ab --engine-a presets/honda_k20.json --engine-b presets/honda_k20.json --dataset out_dataset --label-a baseline --label-b adaptive_on --adaptive-combustion-b on --out ab_compare.json
python -m pywavedyn.cli sensitivity-local --engine presets/honda_k20.json --dataset out_dataset --params ve_scale,friction_scale,burn_scale --out sensitivity_local.json
python -m pywavedyn.cli optimize-guided --engine presets/honda_k20.json --objective dataset_error --params burn_scale,friction_scale --target out_dataset --max-signal-mape power_hp=0.3,torque_nm=0.3 --max-evals 12 --out optimize_guided.json
python -m pywavedyn.cli selfcheck --expectations validation_cases/expectations.json --out selfcheck_report.json
python -m pytest -q -m system
```

Benchmark datasets currently shipped in-repo:

| Engine | Preset | RPM Points | Metric | Contract | Source |
|--------|--------|-----------|--------|----------|--------|
| Honda K20 I4 | `presets/honda_k20.json` | 8 (2k-8k) | Torque + Power MAPE | <= 2% | `regression_golden` |
| Chevy 350 V8 | `presets/chevy_350.json` | 8 (1.5k-5k) | Torque + Power MAPE | <= 2% | `regression_golden` |
| Ferrari F1 V12 | `presets/ferrari_f1.json` | 3 (9k-17k) | Torque + Power MAPE | <= 2% | `regression_golden` |
| Single-cyl Moto | `validation_cases/single_cyl_moto_like.json` | 8 (3k-10k) | Torque + Power MAPE | <= 3% | `regression_golden` |

Limits:
- These in-repo datasets are regression-golden, not external dyno measurements.
- They are useful for regression detection, not for proving absolute fidelity to a real engine.
- Dataset conventions live in `benchmarks/README.md` and `docs/BENCHMARKS_METHOD.md`.
- `selfcheck` is a deterministic sanity and invariant layer, not an external-validation claim.

Current committed real-data package status:
- `benchmarks/datasets/k20_like_real/` and `benchmarks/datasets/v8_like_real/` are the current canonical committed `real_data` packages. They use `metadata.json`, `target_curve.json`, committed `source.csv`, and `source_sha256` traceability.
- `benchmarks/datasets/f1_like_real/` remains a documented placeholder legacy dataset. It is not a canonical committed real-data package and still keeps header-only `targets.csv` as a migration reminder.
- The committed canonical real-data packages are still torque/power-only evidence cases in this repo state. They do not yet prove turbo, fueling, or thermal fidelity.
- The additive dataset/report field `signal_evidence` now makes that explicit through `contract_baseline`, `turbo`, `fueling`, and `thermal` groups.

Interpretation notes:
- `ve_actual` is not identical across all modes. In v1 it is a modeled VE estimate; in v2 it is tied to trapped fresh mass at IVC.
- CLI/GUI dyno-style artifacts that expose `ve_actual` now also carry an additive `observable_semantics.ve_actual` note so the cross-mode caveat travels with the exported JSON.
- Optional plenums, junction capacitance, and wall thermal features are engineering approximations with explicit limits. They improve trend-level modeling, but they should not be read as full 1D resolved junction physics or as a fully validated pulsating-flow thermal envelope.
- Advanced flags remain opt-in by policy; legacy/default behavior should stay stable unless explicitly enabled or compatibility mode is requested.

## Docs
- [docs/README.md](docs/README.md) - user-facing docs index
- [docs/BENCHMARKS_METHOD.md](docs/BENCHMARKS_METHOD.md) - benchmark dataset contract
- [docs/RUNBOOK.md](docs/RUNBOOK.md) - practical setup and execution notes
- [docs/GUI_OVERVIEW.md](docs/GUI_OVERVIEW.md) - GUI overview
- [docs/internal/README.md](docs/internal/README.md) - internal docs, validation detail, audit, and technical notes
- [docs/internal/FEATURES.md](docs/internal/FEATURES.md) - internal feature ledger
- [docs/internal/VALIDATION_GUIDE.md](docs/internal/VALIDATION_GUIDE.md) - internal validation guide

Guided engine creation is available in the GUI through `File -> New Guided Engine...`, with `Basic`, `Advanced`, and `Expert` flows. Dyno, scope, sweep, map, and full-scope paths now share a core preflight validator before execution.

Real dyno workflow is also available in the GUI through the `Real Dyno` tab:
- import CSV/JSON dyno data with explicit mapping and source units
- reuse the last import mapping/units/output folder to reduce repeated setup
- review canonical preview and import warnings
- compare simulator vs real with overlay plots and traceable metrics
- run staged assisted calibration and export the generated artifacts
- run feature validation, explicit A/B comparison, local sensitivity, and dataset-error optimize-guided directly on the loaded dataset
- reopen saved analysis JSON artifacts and export the currently available reports as a bundle
- get a visible busy state while compare/calibration/validation/optimization are running
- inspect outcomes such as `improved`, `tradeoff`, `no_clear_benefit`, and `no_conclusion` without reading raw JSON
- read engineering diagnostics derived from the available signals and report metrics
- migrated analysis artifacts now add an additive common envelope at top level: `report_type`, `report_format_version`, `report_family`, `generated_at_utc`, and `context`
- legacy report fields remain in place; the GUI still supports older standalone artifacts through shape fallback during the transition

Turbo/thermal realism:
- turbo now has an additional opt-in `response_model` for boost build timing; legacy turbo behavior remains unchanged when it is absent
- staged calibration can now use a limited turbo stage when boost evidence exists, tuning only supported level/timing controls
- thermal remains intentionally conservative in this iteration; no new thermal stage is claimed without a stronger comparable signal path

Combustion behavior:
- legacy combustion remains the default path for existing presets
- an opt-in `combustion.adaptive_model` can make burn duration and CA50 respond to RPM, load proxy, compression ratio, boost, configured lambda, residual proxy, and charge temperature
- the adaptive mode is traceable in dyno output and does not replace explicit Wiebe overrides
- `dyno`, `benchmark`, `dyno-compare`, and `calibrate-staged` can force adaptive combustion `as_is`, `on`, or `off` without editing the preset
- staged calibration only tunes the small global subset `adaptive_duration_scale` and `adaptive_ca50_offset_deg`; it does not auto-fit every adaptive coefficient

Preflight behavior:
- Blockers stop execution for non-physical or incomplete configurations.
- Warnings allow execution but flag suspicious RPM, geometry, or tuning ranges for review.

Engineering diagnostics:
- `dyno`, `benchmark` / `dyno-compare`, and `calibrate-staged` can now emit structured diagnostics backed by the signals actually available in each report.
- These diagnostics are interpretive guidance, not experimental proof. Missing channels stay silent instead of generating speculative findings.

Comparative validation:
- `validate-features` runs the existing comparison and staged-calibration infrastructure across one or more canonical datasets without inventing new metrics.
- It compares the supplied baseline against feature toggles that are already implemented in the product:
  - adaptive combustion `on/off`
  - turbo incremental `on/off` when the engine is actually turbocharged
  - staged calibration `before/after`
- Output is intentionally honest per case and per signal:
  - official comparison outcomes shared by backend, GUI, and docs:
  - `improved`
  - `partial_improvement`
  - `tradeoff`
  - `no_clear_benefit`
  - `no_conclusion`
- This layer does not claim global accuracy. It only reports what changed on the scored signals available in each dataset.
- Analysis reports now also include additive `signal_evidence` summaries so each case can say whether turbo/fueling/thermal evidence was actually compared, merely present, or still unavailable in the committed dataset.

A/B comparison and local sensitivity:
- `compare-ab` compares two explicit configurations on the same dataset and reports which scored signals improved, worsened, or traded off.
- `sensitivity-local` runs a small local perturbation around the current configuration and ranks parameter influence by scored signal.
- Current sensitivity is intentionally limited to stable, interpretable knobs already exposed by the model:
  - `ve_scale`
  - `friction_scale`
  - `burn_scale`
  - `adaptive_duration_scale`
  - `adaptive_ca50_offset_deg`
  - `turbo_target_boost_scale`
  - `turbo_spool_rpm_offset`
- The resulting `robustness` labels are only local:
  - official local robustness levels:
  - `low_sensitivity`
  - `moderate_sensitivity`
  - `high_sensitivity`
- They are not a substitute for full uncertainty quantification or statistical confidence intervals.

Guided optimization:
- `optimize` remains the narrow legacy path for runner-length fitting.
- `optimize-guided` adds a small, auditable search over a limited set of interpretable parameters:
  - `intake.runner_length`
  - `ve_scale`
  - `friction_scale`
  - `burn_scale`
  - `adaptive_duration_scale`
  - `adaptive_ca50_offset_deg`
  - `turbo_target_boost_scale`
  - `turbo_spool_rpm_offset`
- Current supported objectives are:
  - `dataset_error`
  - `peak_power`
  - `mean_torque_band`
  - `boost_target_tracking`
- The report includes:
  - baseline
  - explored candidates
  - best feasible candidate
  - constraints used
  - tradeoff notes
  - a locality/fragility warning when top scores are too close
- This is still a bounded local/grid search, not a claim of global optimality.

## More Commands
```bash
python main.py
python -m pywavedyn.cli scope --engine presets/honda_k20.json --rpm 2500 --cycles 1 --out out_scope.json
python -m pywavedyn.cli intake-scope --engine presets/honda_k20.json --target-dx 0.05 --max-steps 200 --out intake_scope.json
python -m pywavedyn.cli audio --engine presets/honda_k20.json --rpm 2500 --duration 0.5 --sample-rate 44100 --out out.wav
python -m pywavedyn.cli sweep --engine presets/honda_k20.json --rpm 3000 --points 5 --out out_sweep.json
python -m pywavedyn.cli map --engine presets/honda_k20.json --rpm-grid 2000,3000 --throttle-grid 0.2,0.6,1.0 --out map.json
python -m pywavedyn.cli cutlist --engine presets/honda_k20.json --out cutlist.json
python -m pywavedyn.cli calibrate --engine presets/honda_k20.json --target target.json --out calib_report.json --max-evals 40 --params ve_scale,friction_scale,burn_scale
python -m pywavedyn.cli full-scope --engine presets/legacy/custom_twin_230cc.json --duration 0.02 --target-dx 0.05 --max-steps 200 --out full_scope.json
python -m pywavedyn.cli optimize --engine presets/legacy/custom_twin_230cc.json --target target.json --param intake.runner_length --bounds 0.20,0.60 --seed 123 --max-evals 30 --out opt_report.json
python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 4000 --turbo presets/turbo_simple.json --out dyno.json
```

## Testing
```bash
python -m pytest
python -m pytest tests/unit
python -m pytest -m integration -q
python -m pytest -m legacy -q
python -m pytest -q tests/test_contract_*.py
```
