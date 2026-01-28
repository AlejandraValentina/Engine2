# PyWaveDyn Documentation

## Overview
PyWaveDyn is a verification-focused 0D virtual dyno plus a 1D exhaust wave-scope (opt-in integration). This document describes the codebase and GUI workflows; "implemented" features are defined by reproducible commands/tests (see FEATURES.md and VALIDATION_GUIDE.md). The advanced core spec lives in `TECHNICAL_SPECS_V2.md`.

## Module Reference

### `core/numerics.py`
- **Responsibilities:** Low-level numerical methods for the 1D Euler equations and valve flow.
- **Key Functions:**
  - `flux_vector` and `lax_wendroff_step` for Lax–Wendroff time marching with geometric source terms.
  - `calculate_mass_flow_rate` for isentropic nozzle/orifice flow (choked/subsonic).
- **Physics:** Euler conservation form, area variation sources, friction placeholders, isentropic mass flow using compressible relations, and safety clamps for stability.

### `core/simulator.py`
- **Responsibilities:** Wrapper around the numerical core to advance a single pipe using boundary conditions sourced from valves or atmosphere.
- **Key Classes:**
  - `PipeSolver` maintains mesh, conserved variables, CFL-based timestep selection, and ghost-cell boundaries.
- **Physics:** Lax-Wendroff scheme, ghost-cell inlet reflection when valves close, ambient static-pressure outlet (P_amb imposed in the ghost cell), energy/density clamping for stability, CFL limiter, and boundary application before/after each step to preserve imposed conditions.

### `core/advanced/*`
- **Responsibilities:** Coupled 0D↔1D solver path with phase-aware boundary fluxes, ghost inversion, and convergence tracking.
- **Key Modules:**
  - `orchestrator.py` (cycle loop, coupling, convergence monitor, optional flags like `use_numba_1d`).
  - `solver_1d.py` (MUSCL–Hancock + Rusanov, outlet BCs, SoA/Numba path).
  - `coupling.py`/`nozzle.py` (valve area, nozzle mass flow, ghost inversion).
  - `cylinder_cv.py`/`combustion.py` (CV update and optional combustion/heat transfer).
  - `junctions.py` (junction mixing + losses).

### `core/thermo.py`
- **Responsibilities:** Zero-dimensional cycle simulation to estimate brake torque and power over a 720° crank cycle.
- **Key Classes:**
  - `CylinderSimulator` builds volume profiles, applies Wiebe heat release, models boosted manifold pressure, runner tuning, Mach-index valve choking, camshaft-timed valve events, and subtracts FMEP friction.
- **Physics:** Slider-crank volume/dV geometry; Wiebe combustion with ignition advance; adiabatic compression/expansion; P·dV work integral; intake/exhaust pumping losses; Mach-index volumetric efficiency with runner length harmonic boosts; valve-timing-based phase masks (IVC/EVO); forced-induction manifold pressure/temperature adjustments; friction mean effective pressure approximation.

### `core/engine_components.py`
- **Responsibilities:** Data model for engine parts with JSON serialization.
- **Key Classes:** `Block`, `CylinderHead`, `Camshaft`, `IntakeSystem`, `ExhaustSystem`, `Supercharger`, `Engine` (root container with save/load helpers).
- **Physics/Data:** Geometric parameters, firing order, displacement computation; cam harmonic lift approximation; redline RPM; flow limits (port flow CFM, throttle CFM).

### `acoustics/audio_generator.py`
- **Responsibilities:** Convert simulated pressure-time signals into listenable audio files.
- **Key Classes:**
  - `AudioSynthesizer` buffers samples, interpolates to 44.1 kHz, high-pass filters, normalizes, and writes WAV.
- **Physics/Signal Processing:** Interp1d resampling, Butterworth high-pass filter for DC removal.

### `gui/main_window.py`
- **Responsibilities:** Main PySide6 window for editing engine data, persisting projects, running dyno sweeps, and exploring parametric optimizations.
- **Key Elements:**
  - Tree-driven component selection with property editors bound directly to dataclasses (including redline RPM, port flow CFM, throttle CFM).
  - Dyno tab with pyqtgraph plotting of power/torque from `CylinderSimulator`, bounded by configurable redline.
  - Optimizer tab to sweep component parameters (cams, intake, exhaust, compression) and plot peak horsepower trends with progress feedback.
  - Toolbar/menu actions for saving/loading JSON configs and quick-save.
- **Workflow:** Refreshes the tree from the `Engine` model, edits values via spin boxes/combo boxes, runs dyno simulations across RPM ranges derived from the block redline, and executes optimization sweeps that temporarily modify component attributes and restore them afterward.

### `gui/widgets/scope_widget.py`
- **Responsibilities:** Plotting helper for pressure/energy traces with HUD text overlay.
- **Key Classes:**
  - `ScopeWidget` provides neon-themed pyqtgraph plot, auto-ranging Y axis, and status text showing simulation time/crank angle/valve state, with thicker neon pen for clarity.

### `test_solver.py`
- **Responsibilities:** Regression harness for the pipe solver to step a simple pipe and log pressures for debugging stability/CFL behavior.

## Usage Guide

### Defining an Engine in the GUI
1. Launch the application (`python main.py`).
2. Use the **Project Explorer** tree to select a component (Block, Head, Camshaft, Intake, Exhaust, Supercharger).
3. The **Properties** tab will auto-focus and show editable fields. Adjust values with spin boxes or combo boxes; changes write directly to the underlying data model. Derived fields (such as displacement and mean piston speed) update in-place without rebuilding the entire form.
4. If a value update fails, the GUI surfaces the error in the status bar and a dialog instead of silently swallowing it.

### Running the Dyno
1. Open the **Dyno Graph** tab.
2. Set the **Redline RPM** in the Block properties to bound the sweep (loop runs from 1000 RPM to the redline + 500 buffer in 500 RPM steps).
3. Click **Run Power Sweep** to simulate; the plot overlays Power (HP) and Torque (Nm) generated by `CylinderSimulator` using the current engine settings.

### Running Headless (CLI)
PyWaveDyn exposes a minimal headless CLI for reproducible runs without the GUI:

- **Dyno sweep:** `python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 2000:9000:250 --out out_dyno.json`
- **Wave scope:** `python -m pywavedyn.cli scope --engine presets/honda_k20.json --rpm 2500 --cycles 1 --out out_scope.json`
- **Intake scope:** `python -m pywavedyn.cli intake-scope --engine presets/honda_k20.json --target-dx 0.05 --max-steps 200 --out intake_scope.json`
- **Audio:** `python -m pywavedyn.cli audio --engine presets/honda_k20.json --rpm 2500 --duration 0.5 --sample-rate 44100 --out out.wav`
- **Sweep:** `python -m pywavedyn.cli sweep --engine presets/honda_k20.json --rpm 3000 --points 5 --out out_sweep.json`
- **Part-load map:** `python -m pywavedyn.cli map --engine presets/honda_k20.json --rpm-grid 2000,3000 --throttle-grid 0.2,0.6,1.0 --out map.json`
- **Cut-list:** `python -m pywavedyn.cli cutlist --engine presets/honda_k20.json --out cutlist.json`
- **Auto-calibration:** `python -m pywavedyn.cli calibrate --engine presets/honda_k20.json --target target.json --out calib_report.json --max-evals 40 --params ve_scale,friction_scale,burn_scale`

The CLI outputs JSON with metadata (input_hash, timestamp, settings, coupling_mode) plus results for each command.

### Recording Audio
Audio can be generated headless via CLI or recorded in the GUI if enabled.

- **CLI:** `python -m pywavedyn.cli audio --engine presets/honda_k20.json --rpm 2500 --duration 0.5 --sample-rate 44100 --out out.wav`
- **GUI:** The scope view can buffer tailpipe pressure samples and export a WAV.

1. During a transient pipe simulation (scope view), enable the **Record Audio** toggle on the toolbar (if present in your build). If the toggle is off, the audio buffer stays empty and **Save Audio** remains disabled.
2. When recording is enabled, each simulation step appends the tailpipe pressure sample via `AudioSynthesizer.add_sample`.
3. Click **Save WAV** to export the buffered signal; pressure is resampled to 44.1 kHz, filtered, normalized, and written as a `.wav` file.

### Saving/Loading JSON Configurations
- **Save:** Use the toolbar save icon or File → Save to write the current `Engine` configuration to JSON via `Engine.save_to_file`. If the project already has a filename, Save writes directly to that path; otherwise it behaves like Save As.
- **Save As:** File → Save As always prompts for a filename.
- **Load:** Use File → Load to restore an existing configuration; the tree and property editors refresh automatically. The window title and overview header show the loaded filename.

### Running Optimization Sweeps
Headless sweeps are available via CLI (runner length grid). GUI sweeps remain available for exploratory workflows.

1. Open the **Optimizer** tab.
2. Choose a target parameter (e.g., intake runner length, cam intake duration, compression ratio) and set start/end/step values.
3. Click **Run Optimization Sweep**. The optimizer temporarily adjusts the selected parameter, runs dyno simulations over the RPM range, records peak horsepower, updates a progress bar, and plots Parameter Value vs. Peak HP.
4. When finished, the original engine settings are restored automatically, so you can adopt the best value manually.

## Verificacion v2.3 FINAL
```bash
python -m pytest -q -W error::RuntimeWarning
python -m pytest -q
python -m pytest -q -m integration
python -m pytest -q -m legacy
python -m pytest -q -m perf
python -m pytest -q -m system
python -m pywavedyn.cli --help
python -m pywavedyn.cli full-scope --help
python -m pywavedyn.cli benchmark --help
python -m pywavedyn.cli dyno --help
python -m pywavedyn.cli optimize --help
```

### Notes on Physics Models
- **Gas Dynamics:** Pipes advance with a Lax–Wendroff finite-volume scheme, ghost cells for boundary reflection, ambient static-pressure outlets (P_amb imposed in the ghost cell), and stability clamps (density/energy, CFL timestep).
- **Valve Flow:** Mass transfer uses isentropic relations with choking detection and discharge coefficients. The default 1D exhaust valve model uses curtain or fixed seat area (via `SimulationSettings.exhaust_valve_area_model`) with Cd from `SimulationSettings.exhaust_valve_cd` (override) or `CylinderHead.exhaust_valve_cd` and `CylinderHead.exhaust_valve_seat_diameter_mm`. The placeholder sinusoid is only used when valve geometry/cam data is unavailable or explicitly forced.
- **Thermo Cycle:** Cylinder pressure uses phase-aware intake/compression/combustion/exhaust masks with Wiebe heat release and friction torque subtraction for brake output.
- **Audio:** Raw pressure histories are interpolated to fixed-rate audio with optional DC removal to hear exhaust timbre.
