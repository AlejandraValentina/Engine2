# PyWaveDyn – Professional 1D Gas Dynamics & Engine Simulator

PyWaveDyn is a calibrated open-source tool for simulating internal combustion engines. It combines a 0D thermodynamic virtual dyno, a 1D wave-based CFD scope, and fabrication/optimizer utilities for rapid iteration from concept to shop floor.

## Key Features
- **Virtual Dyno** – 0D Otto-cycle solver with Wiebe combustion, Woschni heat transfer, Chen–Flynn friction, knock awareness, and Mach-index choking to predict brake torque/HP across RPM.
- **Wave Scope** – Real-time visualization of pressure waves in intake/exhaust runners using a 1D Euler solver (Lax–Wendroff + ghost cells, junction coupling) for tuning header lengths and collectors.
- **Acoustics** – Polyphonic exhaust sound synthesis that mixes per-cylinder pressure traces by firing order for realistic engine audio.
- **Optimizer** – Parameter sweeps for cams, ignition, airflow, boost, and runner/header geometry to locate peak power regions.
- **Fabrication** – Header cut-list assistance with per-cylinder target/actual lengths, collector guidance, and quick reports for shop builds.
- **Validated Physics** – Calibrated against representative engines (Honda K20, Chevy small-block, Ferrari V12, kart 125 cc) with configurable friction, combustion, and airflow parameters.

## Installation & Usage
1. **Prerequisites:** Python 3.10+.
2. **Install dependencies:**
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

## Physics Overview
- **Thermodynamics (0D):** Four-stroke phasing with Wiebe combustion (configurable a/m, burn duration, ignition advance), Woschni wall heat transfer, Chen–Flynn FMEP (A/B/C coefficients with user scaling), and Mach-index flow choking tied to valve geometry/port flow efficiency.
- **Wave Dynamics (1D):** Euler equations with Lax–Wendroff integration, Darcy–Weisbach friction source, and ghost-cell boundaries for valves/outlets plus junction collectors for multi-cylinder exhausts.
- **Airflow & Environment:** Configurable intake temp/pressure, intercooler efficiency, throttle/port flow limits, and Mach tolerance to capture altitude and hardware effects.
- **Coupling:** 0D dyno operates independently for torque/HP; 1D scope uses cylinder pressure history as a one-way boundary for visualization/acoustics.

For deep technical details and implementation contracts, see [TECHNICAL_DOCS.md](TECHNICAL_DOCS.md).

## Project Structure
- **core/** – Physics and data models (`thermo.py` for 0D cycle, `simulator.py`/`junctions.py` for 1D wave network, `numerics.py` for jitted flux/solver kernels, `engine_components.py` for serialized engine schema).
- **gui/** – PySide6 application with project explorer, properties editor, dyno/optimizer, wave scope, fabrication planner, and audio controls.
- **acoustics/** – WAV synthesis utilities.
- **tests/** – Unit/integration suites covering physics identities, trends, and engine presets.
- ***.json** – Example engine configurations (NA/turbo, small/large displacement) ready to load in the GUI.

## Screenshots
_Add your screenshots here to showcase the interface._

## License & Contributions
PyWaveDyn is an open-source engineering tool. Contributions, validation data, and new presets are welcome via issues and pull requests.
