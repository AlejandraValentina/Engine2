# VALIDATION_GUIDE

A) Default repo suite (must be green)
- `python -m pytest -q`

B) Warnings strict
- `python -m pytest -q -W error::RuntimeWarning`

C) Fast dev loop
- `python -m pytest -q -m "not slow"`

D) Pro dyno focus
- `python -m pytest -q -W error::RuntimeWarning -k pro_dyno`

E) Verificacion v2.2
- `python -m pytest -q -W error::RuntimeWarning`
- `python -m pytest -q`
- `python -m pytest -q -m integration`
- `python -m pytest -q -m legacy`
- `python -m pytest -q -m perf`

F) Verificacion v2.3 FINAL
- `python -m pytest -q -W error::RuntimeWarning`
- `python -m pytest -q`
- `python -m pytest -q -m integration`
- `python -m pytest -q -m legacy`
- `python -m pytest -q -m system`
- `python -m pywavedyn.cli selfcheck --expectations validation_cases/expectations.json --out selfcheck_report.json`

F.1) Verificacion v2.0
- `python -m pytest -m integration -q tests/integration/test_0d_1d_bidirectional_backpressure_affects_cycle.py`
- `python -m pytest -q tests/test_audio_multicyl_wav_nonempty.py`
- `python -m pytest -q tests/test_headless_sweep_runner_length.py`
- `python -m pytest -q tests/test_cutlist_cli_generates_expected_keys.py`
- `python -m pytest -q -m legacy`

G) Benchmarks
- `python -m pywavedyn.cli benchmark --engine presets/honda_k20.json --dataset benchmarks/datasets/honda_k20_na --out bench_report.json`
- Regression-golden datasets:
  - `python -m pywavedyn.cli benchmark --engine presets/chevy_350.json --dataset benchmarks/datasets/chevy_350_na --out bench_report.json`
  - `python -m pywavedyn.cli benchmark --engine presets/ferrari_f1.json --dataset benchmarks/datasets/ferrari_f1_na --out bench_report.json`
  - `python -m pywavedyn.cli benchmark --engine validation_cases/single_cyl_moto_like.json --dataset benchmarks/datasets/single_cyl_moto_na --out bench_report.json`
  - `python -m pywavedyn.cli benchmark --engine presets/honda_k20.json --dataset benchmarks/datasets/k20_like_regression_golden --out bench_report.json`
  - `python -m pywavedyn.cli benchmark --engine presets/chevy_350.json --dataset benchmarks/datasets/v8_like_regression_golden --out bench_report.json`
  - `python -m pywavedyn.cli benchmark --engine presets/ferrari_f1.json --dataset benchmarks/datasets/f1_like_regression_golden --out bench_report.json`
- Importador (CSV -> targets):
  - `python -m pywavedyn.cli bench-import --csv curve.csv --out benchmarks/datasets/<name>/target_curve.json --engine-id <id> --torque-units lbft --power-units hp`

Notes
- `regression_golden` datasets are generated from current simulator outputs and used for stability/regression.
- `real_data` datasets (not included in repo) should be stored externally and imported via `bench-import`.

H) Runbook quick check
- Install deps: `python -m pip install -r requirements.txt`
- Dev/test deps: `python -m pip install -r requirements-dev.txt`
- Gates:
  - `python -m pytest -q`
  - `python -m pytest -q -W error::RuntimeWarning`
  - `python -m pytest -q -m integration`
  - `python -m pytest -q -m legacy`
  - `python -m pytest -q -m system`
- GUI smoke (offscreen):
  - `QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_gui_import_smoke.py tests/test_gui_offscreen_window_smoke.py`

H) Scavenging metrics (intake_coupling)
- `overlap_flow_kg`: estimacion de masa intercambiada durante overlap, derivada de fraccion de overlap y caudal.
- `residual_fraction_est`: fraccion residual estimada = overlap_flow_kg / masa fresca por ciclo.
- `scavenging_index`: 1 - residual_fraction_est (mayor es mejor).

Notes
- 2026-01-27: Updated integration baseline bands (BMEP/VE/HP) to reflect current 0D calibration with valve-area penalty and revised friction scaling. Adjusted expectations document the new steady-state outputs without changing default feature flags.
