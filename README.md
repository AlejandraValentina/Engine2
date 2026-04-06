# PyWaveDyn - Professional 1D Gas Dynamics & Engine Simulator

PyWaveDyn is a verification-focused engine simulation project with a 0D virtual dyno, a 1D gas-dynamics scope, and reproducible CLI workflows for benchmarks, selfcheck, sweeps, and reports.

## What PyWaveDyn Is
- 0D dyno for brake torque and power sweeps.
- 1D wave tooling for scope-style pressure analysis.
- CLI-first validation surface with schema-backed JSON outputs.
- GUI available, but CLI/tests are the source of truth for validated behavior.

Project maturity is tracked in `docs/internal/FEATURES.md` and `docs/internal/VALIDATION_GUIDE.md`.

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

## Advanced Core (v2)
The v2.0 Advanced Physics Core lives in `core/advanced/` and runs in parallel with v1 (Quick Dyno).

**Toy demo:** `python scripts/run_v2_toy.py`

**Tests:**
- Unit: `pytest -q`
- Integration (opt-in): `pytest -q -m integration`

**Spec & flags:** see `docs/TECHNICAL_SPECS_V2.md` for the coupling contract and optional flags
(`use_numba_1d`, `combustion.enabled`, `heat_transfer.enabled`, `outlet_mode`, under-relaxation).

**Full-feature demo preset:** `presets/v2_full_features_demo.json`
Run a short advanced case with optional flags wired in:
```bash
python examples/run_v2_full_features_demo.py
```
This writes `out_v2_demo.json` with convergence history and summary metrics.

Manual wiring (if you prefer a notebook or custom runner):
```bash
python - <<'PY'
import json
import math

from core.engine_components import Engine
from core.advanced.coupling import ValveTiming
from core.advanced.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    PipePrefillConfig,
    PipePrefillState,
    ValveClosedWallBCConfig,
)

cfg = json.load(open("presets/v2_full_features_demo.json", "r", encoding="utf-8"))
engine = Engine.from_dict(cfg)

prefill = cfg["pipe_prefill"]
pipe_prefill = PipePrefillConfig(
    enabled=True,
    intake=PipePrefillState(**prefill["intake"]),
    exhaust=PipePrefillState(**prefill["exhaust"]),
)
wall_bc = ValveClosedWallBCConfig(**cfg["valve_closed_wall_bc"])

orc = Orchestrator(
    OrchestratorConfig(
        cp_model=engine.simulation_settings.cp_model,
        throttle=engine.throttle,
        pipe_prefill=pipe_prefill,
        valve_closed_wall_bc=wall_bc,
    )
)

seat_mm = engine.head.exhaust_valve_seat_diameter_mm or engine.head.exhaust_valve_diameter
valve = ValveTiming(
    open_start_deg=360.0,
    open_end_deg=540.0,
    max_lift_m=engine.camshaft.exhaust_lift * 1e-3,
    seat_diameter_m=seat_mm * 1e-3,
    cd=0.9,
)

bore_m = engine.block.bore * 1e-3
stroke_m = engine.block.stroke * 1e-3
conrod_m = engine.block.conrod_length * 1e-3
area = math.pi * (bore_m * 0.5) ** 2
clearance_m3 = area * stroke_m / max(engine.head.compression_ratio - 1.0, 1e-6)

result = orc.run(
    rpm=3000.0,
    pipe_cells=30,
    pipe_length_m=0.6,
    pipe_diameter_m=0.04,
    bore_m=bore_m,
    stroke_m=stroke_m,
    conrod_m=conrod_m,
    clearance_m3=clearance_m3,
    valve=valve,
)
print("indicated_work", result["indicated_work"][-1])
PY
```

## Physics Overview
- **Thermodynamics (0D):** Four-stroke phasing with Wiebe combustion (configurable a/m, burn duration, ignition advance), Woschni wall heat transfer, Chen-Flynn FMEP (A/B/C coefficients with user scaling), and Mach-index flow choking tied to valve geometry/port flow efficiency.
- **Wave Dynamics (1D):** Euler equations with Lax-Wendroff integration, Darcy-Weisbach friction source, and ghost-cell boundaries for valves/outlets plus junction collectors for multi-cylinder exhausts. Legacy coupling is one-way; the advanced core adds an opt-in coupled 0D<->1D path (see `docs/TECHNICAL_SPECS_V2.md`).
- **Airflow & Environment:** Configurable intake temp/pressure, intercooler efficiency, throttle/port flow limits, and Mach tolerance to capture altitude and hardware effects.
- **Coupling:** Legacy dyno operates independently for torque/HP; the advanced core provides a coupled path for 0D<->1D exchange (opt-in).

## Project Structure
- **core/** - Physics and data models (`thermo.py` for 0D cycle, `simulator.py`/`junctions.py` for 1D wave network, `numerics.py` for jitted flux/solver kernels, `engine_components.py` for serialized engine schema).
- **gui/** - PySide6 application with project explorer, properties editor, dyno/optimizer, wave scope, fabrication planner, and audio controls.
- **acoustics/** - WAV synthesis utilities.
- **tests/** - Unit/integration suites covering physics identities, trends, and engine presets.
- **presets/** - Example engine configurations (NA/turbo, small/large displacement) ready to load in the GUI.

## Screenshots
_Add your screenshots here to showcase the interface._

## License & Contributions
SPDX-License-Identifier: MIT  
License: MIT (see LICENSE). Contributions, validation data, and new presets are welcome via issues and pull requests.
