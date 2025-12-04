# PyWaveDyn – Professional 1D Gas Dynamics & Engine Simulator

PyWaveDyn is a verification-focused open-source tool for simulating internal combustion engines. It combines a 0D thermodynamic virtual dyno, a 1D wave solver (Euler 1D, finite-volume Lax–Wendroff + ghost cells), and fabrication/optimizer utilities for rapid iteration from concept to shop floor.

## Key Features
- **Virtual Dyno** – 0D Otto-cycle solver with Wiebe combustion, Woschni heat transfer, Chen–Flynn friction, knock awareness, and Mach-index choking to predict brake torque/HP across RPM.
- **Wave Scope** – Visualization of pressure waves in exhaust runners/headers (primaries/collector/tailpipe) using a 1D Euler solver (Lax–Wendroff + ghost cells, junction coupling) for tuning header lengths and collectors. Current 1D network scope: exhaust only; intake handled in 0D.
- **Acoustics** – Polyphonic exhaust sound synthesis that mixes per-cylinder pressure traces by firing order for engine audio.
- **Optimizer** – Parameter sweeps for cams, ignition, airflow, boost, and runner/header geometry to locate peak power regions.
- **Fabrication** – Header cut-list assistance with per-cylinder target/actual lengths, collector guidance, and quick reports for shop builds.
- **Verification & Presets** – Includes example presets (K20, V8, V12, kart) used for regression sanity checks with configurable friction, combustion, and airflow parameters.

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
7. **Export audio (optional):** Use the Wave tab to save a synthesized WAV from the exhaust pulses.
8. **Run tests:**
   ```bash
   python -m pytest
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
License: TODO (add SPDX identifier and LICENSE file). Contributions, validation data, and new presets are welcome via issues and pull requests.
