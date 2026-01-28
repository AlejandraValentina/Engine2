# PyWaveDyn – Professional 1D Gas Dynamics & Engine Simulator

PyWaveDyn is a verification-focused open-source tool for simulating internal combustion engines. It combines a 0D thermodynamic virtual dyno, a 1D wave solver (Euler 1D, finite-volume Lax–Wendroff + ghost cells), and planned/prototype optimizer/fabrication utilities for rapid iteration from concept to shop floor (see FEATURES.md).

## Project Status (source of truth)
“Implemented” means reproducible via a command and/or covered by green tests.
See: FEATURES.md and VALIDATION_GUIDE.md.

### Implemented & validated
- 0D virtual dyno with verification-focused tests.
- 1D exhaust scope solver available as an opt-in integration contract.
- Physics identities/trends/sanity test suite and canonical presets audit.
- Multi-cylinder audio synthesis via headless CLI/tests.
- Headless parameter sweeps via CLI/tests.
- Reproducible cut-list generation via CLI/tests.

### Prototype (GUI-first)
- GUI-driven parameter sweeps/optimizer workflows (CLI is the source of truth for validated features).
- Fabrication UI/planner utilities (CLI cut-list is the validated path).

## Key Features
- **Virtual Dyno (0D)** – Otto-cycle solver with explicit combustion/loss models and verification tests to predict brake torque/HP across RPM.
- **Wave Scope (1D)** - Pressure-wave visualization for exhaust networks (current scope: exhaust only; intake handled in 0D). Legacy scope is one-way; the advanced core provides an opt-in coupled 0D↔1D path (see `docs/TECHNICAL_SPECS_V2.md`).
- **Acoustics** - Multi-cylinder WAV synthesis via headless CLI/tests.
- **Optimizer** - Headless CLI sweeps for parameter studies (runner length grid).
- **Fabrication** - Reproducible cut-list output via CLI/tests.
- **Verification & Presets** – Canonical presets and regression/contract tests with a validation guide for reproducible runs.

## Installation & Quickstart
1. **Prerequisites:** Python 3.10+.
2. **Install dependencies (deterministic order):**
   ```bash
   python -m pip install -r requirements.txt
   ```
   For development and tests:
   ```bash
   python -m pip install -r requirements-dev.txt
   ```
3. **Run the GUI:**
   ```bash
   python main.py
   ```
4. **Load a preset:** From the GUI, open an example JSON from `presets/` (e.g., K20/V8/V12).
5. **Run a dyno sweep (CLI):**
   ```bash
   python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 2000:9000:250 --out out_dyno.json
   ```
6. **Wave scope (CLI):**
   ```bash
   python -m pywavedyn.cli scope --engine presets/honda_k20.json --rpm 2500 --cycles 1 --out out_scope.json
   ```
7. **Intake scope (CLI):**
   ```bash
   python -m pywavedyn.cli intake-scope --engine presets/honda_k20.json --target-dx 0.05 --max-steps 200 --out intake_scope.json
   ```
7. **Export audio (CLI):**
   ```bash
   python -m pywavedyn.cli audio --engine presets/honda_k20.json --rpm 2500 --duration 0.5 --sample-rate 44100 --out out.wav
   ```
8. **Headless sweep (CLI):**
   ```bash
   python -m pywavedyn.cli sweep --engine presets/honda_k20.json --rpm 3000 --points 5 --out out_sweep.json
   ```
9. **Part-load map (CLI):**
   ```bash
   python -m pywavedyn.cli map --engine presets/honda_k20.json --rpm-grid 2000,3000 --throttle-grid 0.2,0.6,1.0 --out map.json
   ```
9. **Cut-list (CLI):**
   ```bash
   python -m pywavedyn.cli cutlist --engine presets/honda_k20.json --out cutlist.json
   ```
10. **Auto-calibration (CLI):**
   ```bash
   python -m pywavedyn.cli calibrate --engine presets/honda_k20.json --target target.json --out calib_report.json --max-evals 40 --params ve_scale,friction_scale,burn_scale
   ```
11. **Run tests:**
   ```bash
   python -m pytest
   ```
12. **Run selfcheck (validation cases):**
   ```bash
   python -m pywavedyn.cli selfcheck --expectations validation_cases/expectations.json --out selfcheck_report.json
   ```

## Verificacion v2.1
```bash
python -m pytest -q
python -m pytest -q -W error::RuntimeWarning
python -m pytest -q -m integration
python -m pytest -q -m legacy
python -m pywavedyn.cli --help
python -m pywavedyn.cli intake-scope --help
python -m pywavedyn.cli map --help
python -m pywavedyn.cli calibrate --help
```

## Run Demo
Preset: `presets/v2_full_features_demo.json`  
```bash
python examples/run_v2_full_features_demo.py
```
Writes `out_v2_demo.json`.

## Docs
- [TECHNICAL_DOCS.md](TECHNICAL_DOCS.md) – especificación técnica de modelos 0D/1D.
- [DOCUMENTATION.md](DOCUMENTATION.md) – guía general y notas de arquitectura.
- [VISION.md](VISION.md) – visión del proyecto.
- [FEATURES.md](FEATURES.md) – checklist verificable de funcionalidades.
- [VALIDATION_GUIDE.md](VALIDATION_GUIDE.md) – cómo ejecutar las validaciones y criterios de “implementado”.
- [AUDIT_REPORT.md](AUDIT_REPORT.md) – inventario de presets y estado de pruebas.

## Testing
- Instalar dependencias base: `python -m pip install -r requirements.txt`
- Dependencias de desarrollo/tests: `python -m pip install -r requirements-dev.txt`
- Suite completa: `python -m pytest`
- Unit tests: `python -m pytest tests/unit`
- Integracion (opt-in): `python -m pytest -m integration -q`
- Legacy (opt-in): `python -m pytest -m legacy -q`
- Contratos rápidos: `python -m pytest -q tests/test_contract_*.py`
- Identidades/Tendencias/Sanidad: `python -m pytest -q tests/test_identities.py` | `tests/test_trends.py` | `tests/test_sanity_bands.py`

## Advanced Core (v2)
The v2.0 Advanced Physics Core lives in `core/advanced/` and runs in parallel with v1 (Quick Dyno).

**Toy demo:**\n`python scripts/run_v2_toy.py`

**Tests:**\n- Unit: `pytest -q`\n- Integration (opt-in): `pytest -q -m integration`

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
- **Thermodynamics (0D):** Four-stroke phasing with Wiebe combustion (configurable a/m, burn duration, ignition advance), Woschni wall heat transfer, Chen–Flynn FMEP (A/B/C coefficients with user scaling), and Mach-index flow choking tied to valve geometry/port flow efficiency.
- **Wave Dynamics (1D):** Euler equations with Lax-Wendroff integration, Darcy-Weisbach friction source, and ghost-cell boundaries for valves/outlets plus junction collectors for multi-cylinder exhausts. Legacy coupling is one-way; the advanced core adds an opt-in coupled 0D↔1D path (see `docs/TECHNICAL_SPECS_V2.md`).
- **Airflow & Environment:** Configurable intake temp/pressure, intercooler efficiency, throttle/port flow limits, and Mach tolerance to capture altitude and hardware effects.
- **Coupling:** Legacy dyno operates independently for torque/HP; the advanced core provides a coupled path for 0D↔1D exchange (opt-in).

## Project Structure
- **core/** – Physics and data models (`thermo.py` for 0D cycle, `simulator.py`/`junctions.py` for 1D wave network, `numerics.py` for jitted flux/solver kernels, `engine_components.py` for serialized engine schema).
- **gui/** – PySide6 application with project explorer, properties editor, dyno/optimizer, wave scope, fabrication planner, and audio controls.
- **acoustics/** – WAV synthesis utilities.
- **tests/** – Unit/integration suites covering physics identities, trends, and engine presets.
- **presets/** – Example engine configurations (NA/turbo, small/large displacement) ready to load in the GUI.

## Screenshots
_Add your screenshots here to showcase the interface._

## License & Contributions
SPDX-License-Identifier: MIT  
License: MIT (see LICENSE). Contributions, validation data, and new presets are welcome via issues and pull requests.
