# APP_SERIA_CHECKLIST

Checklist reproducible para verificar wiring end-to-end (GUI + CLI + core) sin cambiar defaults.

## 1) Mapa CLI -> core

Subcomando | Core runner / módulo
---|---
dyno v1 | `pywavedyn.cli._dyno_results_v1` → `core.thermo.CylinderSimulator`
dyno v2 | `pywavedyn.cli._dyno_results_v2` → `core.pro_dyno_v2.ProDynoV2Runner`
scope | `pywavedyn.cli.run_scope` → `core.simulator.PipeSolver` + `core.wave_utils.compute_pressure_matrix`
intake-scope | `pywavedyn.cli.run_intake_scope` → `core.intake_scope.run_intake_scope`
audio | `pywavedyn.cli.run_audio` → `acoustics.audio_generator.save_multicylinder_wav`
sweep | `pywavedyn.cli.run_sweep` → `core.sweep.run_sweep_runner_length`
map | `pywavedyn.cli.run_map` → `core.map_runner.run_partload_map`
calibrate | `pywavedyn.cli.run_calibrate` → `core.auto_calibration.calibrate_engine`
calibrate (diagnostics) | `pywavedyn.cli.run_calibrate` → `core.auto_calibration.calibrate_engine_diagnostics`
optimize | `pywavedyn.cli.run_optimize` → `core.optimize.optimize_runner_length`
full-scope | `pywavedyn.cli.run_full_scope` → `core.full_network.run_full_scope`
cutlist | `pywavedyn.cli.run_cutlist` → `core.cutlist.generate_cutlist`
selfcheck | `pywavedyn.cli.run_selfcheck` → `validation_cases/expectations.json`
benchmark | `pywavedyn.cli.run_benchmark` → `pywavedyn.bench.evaluate`
bench-import | `pywavedyn.cli.run_bench_import` → `pywavedyn.bench_import.write_dataset_package`
dyno-import | `pywavedyn.cli.run_dyno_import` → `pywavedyn.dyno_data.write_dataset_package`
dyno-compare | `pywavedyn.cli.run_dyno_compare` → `pywavedyn.bench.evaluate`
calibrate-staged | `pywavedyn.cli.run_calibrate_staged` → `pywavedyn.staged_calibration.run_staged_calibration`

## 2) Mapa GUI -> core

GUI flow | Core runner / módulo
---|---
Quick Dyno (v1) | `gui.main_window.run_dyno_sweep` → `core.thermo.CylinderSimulator`
Pro Dyno (v2) | `gui.main_window.run_dyno_sweep` → `core.pro_dyno_v2.ProDynoV2Runner`
Export Dyno JSON | `gui.main_window.export_dyno_json` → schema `schemas/dyno.schema.json`
Load/Save preset | `Engine.save_to_file` / `Engine.from_dict`

## 3) Comandos reproducibles (CLI)

Command | Output | Acceptance
---|---|---
`python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 3000 --out dyno.json` | `dyno.json` | schema `schemas/dyno.schema.json`, sin NaN/inf
`python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 3000 --mode v2 --out dyno_v2.json` | `dyno_v2.json` | schema `schemas/dyno.schema.json`, coupling_mode=v2_orchestrator
`python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 3000 --mode v2 --knock-report knock.json --out dyno.json` | `knock.json` | schema `schemas/knock_report.schema.json`, requiere residuals enabled
`python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 1000:9000:500 --mode v2 --settle-cycles 1 --min-periodicity 0.35 --drop-invalid --rpm-start-safe --out dyno_v2_stable.json` | `dyno_v2_stable.json` | puntos inválidos filtrados, sin torque negativo
`python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 4000 --turbo presets/turbo_simple.json --out dyno_turbo.json` | `dyno_turbo.json` | schema ok, power > NA
`python -m pywavedyn.cli dyno --engine presets/legacy/custom_twin_230cc.json --rpm 2000 --auto-legacy-compat --out dyno_legacy.json` | `dyno_legacy.json` | `metadata.legacy_compat=\"v1\"` presente
`python -m pywavedyn.cli intake-scope --engine presets/honda_k20.json --out intake_scope.json` | `intake_scope.json` | schema ok, sin NaN/inf
`python -m pywavedyn.cli calibrate --engine presets/honda_k20.json --target target.json --out calib_report.json` | `calib_report.json` | schema `schemas/calib_report.schema.json`
`python -m pywavedyn.cli calibrate --engine presets/honda_k20.json --target target.json --out calibrate_report.json --diagnostics --multi-start 2 --top-k 3 --seed 123` | `calibrate_report.json` | schema `schemas/calibrate_report.schema.json`, `uniqueness.unique` presente
`python -m pywavedyn.cli benchmark --engine presets/honda_k20.json --dataset benchmarks/datasets/honda_k20_na --out bench_report.json` | `bench_report.json` | schema ok, contract pass

## 3.1) Legacy regression (golden)

Command | Output | Acceptance
---|---|---
`python -m pytest -q tests/system/test_legacy_compat_golden_regression.py` | tests | compara BMEP/power/torque/VE vs golden (legacy_compat v1)

## 3.2) Validation interpretation

Check | What it covers | What it does not cover
---|---|---
`selfcheck` | deterministic expectations, finite outputs, physical-invariant guards, lightweight relational checks | external dyno fidelity
`benchmark` with in-repo datasets | regression-golden drift detection | real-world accuracy outside those references
`dyno-import` + `dyno-compare` + calibration | traceable comparison against imported dyno measurements | global solver validity for all operating conditions

## 4) GUI smoke (offscreen)

Command | Output | Acceptance
---|---|---
`QT_QPA_PLATFORM=offscreen python -m pytest -q tests/test_gui_import_smoke.py tests/test_gui_offscreen_window_smoke.py` | tests | pass/skip only if PySide6 missing
`QT_QPA_PLATFORM=offscreen python -m pytest -q tests/system/test_gui_export_dyno_schema.py` | `dyno.json` | schema ok
`QT_QPA_PLATFORM=offscreen python -m pytest -q tests/system/test_gui_export_dyno_schema_v2.py` | `dyno_v2.json` | schema ok, coupling_mode=v2_orchestrator

## 5) Opt-in flags (wiring)

Flag | Where | Expected
---|---|---
`turbo` | `--turbo` in `dyno` | power trend > NA, schema ok
`intake_plenum.wall_thermal` | config in engine JSON | `T_wall` updates (internal), no NaN/inf
`calibrate --diagnostics` | CLI calibrate | `calibrate_report.schema.json` valid, uniqueness fields present
`simulation_settings.species.enabled` | engine JSON | 1D conserva `Y_fresh` en rutas opt-in
`--knock-report` | CLI dyno | reporte separado, schema `knock_report.schema.json`
`--legacy-compat v1` / `--auto-legacy-compat` | CLI | aplica perfil v1 (solo opt-in)

## 6) Gates

```bash
python -m pytest -q
python -m pytest -q -W error::RuntimeWarning
python -m pytest -q -m integration
python -m pytest -q -m legacy
python -m pytest -q -m system
```
