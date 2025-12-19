# PyWaveDyn – Professional 1D Gas Dynamics & Engine Simulator

PyWaveDyn is a verification-focused open-source tool for simulating internal combustion engines. It combines a 0D thermodynamic virtual dyno, a 1D wave solver (Euler 1D, finite-volume Lax–Wendroff + ghost cells), and planned/prototype optimizer/fabrication utilities for rapid iteration from concept to shop floor (see FEATURES.md).

## Project Status (source of truth)
“Implemented” means reproducible via a command and/or covered by green tests.
See: FEATURES.md and VALIDATION_GUIDE.md.

### Implemented & validated
- 0D virtual dyno with verification-focused tests.
- 1D exhaust scope solver available as an opt-in integration contract.
- Physics identities/trends/sanity test suite and canonical presets audit.

### Prototype (may exist in GUI, not guaranteed by CLI/tests)
- Audio tooling wired to simulated pressure traces (coverage may be incomplete).
- GUI-driven parameter sweeps/optimizer workflows.
- Fabrication UI/planner utilities (if present).

### Not implemented yet (per checklist)
- Bidirectional 0D↔1D coupling affecting the 0D cycle.
- Verified multi-cylinder polyphonic audio via CLI/tests.
- Headless (no-GUI) parameter sweeps via CLI/tests.
- Reproducible cut-list/BOM generation via CLI/tests.

## Key Features
- **Virtual Dyno (0D)** – Otto-cycle solver with explicit combustion/loss models and verification tests to predict brake torque/HP across RPM.
- **Wave Scope (1D)** – Pressure-wave visualization for exhaust networks (current scope: exhaust only; intake handled in 0D). Integration is opt-in and does not back-feed the 0D cycle.
- **Acoustics (prototype)** – Audio utilities driven by simulated pressure traces; verification/CLI coverage may be incomplete (see FEATURES.md).
- **Optimizer (prototype)** – GUI-first parameter sweeps; headless CLI sweeps are not yet part of the validated toolchain (see FEATURES.md).
- **Fabrication (planned/prototype)** – Cut-list/BOM style outputs are not yet guaranteed reproducible by CLI/tests (see FEATURES.md).
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
5. **Run a dyno sweep:** Use the Dyno tab to generate HP/Torque curves.
6. **Wave scope:** Run a wave calculation on the exhaust network and scrub the results.
7. **Export audio (optional):** If present in your build, use the Wave tab to save a WAV from simulated exhaust pressure traces (verification coverage may be incomplete; see FEATURES.md).
8. **Run tests:**
   ```bash
   python -m pytest
   ```
9. **Run selfcheck (validation cases):**
   ```bash
   python -m pywavedyn.cli selfcheck --expectations validation_cases/expectations.json --out selfcheck_report.json
   ```

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
- Integración (opt-in): `python -m pytest tests/integration` o `python -m pytest -m integration`
- Contratos rápidos: `python -m pytest -q tests/test_contract_*.py`
- Identidades/Tendencias/Sanidad: `python -m pytest -q tests/test_identities.py` | `tests/test_trends.py` | `tests/test_sanity_bands.py`

## Advanced Core (v2)
The v2.0 Advanced Physics Core lives in `core/advanced/` and runs in parallel with v1 (Quick Dyno).

**Toy demo:**\n`python scripts/run_v2_toy.py`

**Tests:**\n- Unit: `pytest -q`\n- Integration (opt-in): `pytest -q -m integration`

## Physics Overview
- **Thermodynamics (0D):** Four-stroke phasing with Wiebe combustion (configurable a/m, burn duration, ignition advance), Woschni wall heat transfer, Chen–Flynn FMEP (A/B/C coefficients with user scaling), and Mach-index flow choking tied to valve geometry/port flow efficiency.
- **Wave Dynamics (1D):** Euler equations with Lax–Wendroff integration, Darcy–Weisbach friction source, and ghost-cell boundaries for valves/outlets plus junction collectors for multi-cylinder exhausts. Current coupling is one-way: the 0D dyno provides cylinder pressure traces as inlet boundaries; there is no feedback from the 1D scope to the 0D solver.
- **Airflow & Environment:** Configurable intake temp/pressure, intercooler efficiency, throttle/port flow limits, and Mach tolerance to capture altitude and hardware effects.
- **Coupling:** 0D dyno operates independently for torque/HP; 1D scope uses cylinder pressure history as a one-way boundary for visualization/acoustics.

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
