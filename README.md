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

## Docs
- [docs/README.md](docs/README.md) - user-facing docs index
- [docs/BENCHMARKS_METHOD.md](docs/BENCHMARKS_METHOD.md) - benchmark dataset contract
- [docs/RUNBOOK.md](docs/RUNBOOK.md) - practical setup and execution notes
- [docs/GUI_OVERVIEW.md](docs/GUI_OVERVIEW.md) - GUI overview
- [docs/internal/README.md](docs/internal/README.md) - internal docs, validation detail, audit, and technical notes

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
