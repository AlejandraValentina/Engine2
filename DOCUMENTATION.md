# PyWaveDyn Documentation

## Overview
PyWaveDyn is a one-dimensional gas-dynamics simulator and virtual dyno for internal combustion engines. It couples fast finite-volume pipe solvers, zero-dimensional cylinder thermodynamics, audio synthesis, and a PySide6 GUI to let you configure engines, run power sweeps, optimize component parameters, and export exhaust sound.

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
- **Physics:** Lax–Wendroff scheme, ghost-cell inlet reflection when valves close, transmissive outlet, energy/density clamping for stability, CFL limiter, and boundary application before/after each step to preserve imposed conditions.

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
3. The **Properties** tab will auto-focus and show editable fields. Adjust values with spin boxes or combo boxes; changes write directly to the underlying data model.

### Running the Dyno
1. Open the **Dyno Graph** tab.
2. Set the **Redline RPM** in the Block properties to bound the sweep (loop runs from 1000 RPM to the redline + 500 buffer in 500 RPM steps).
3. Click **Run Power Sweep** to simulate; the plot overlays Power (HP) and Torque (Nm) generated by `CylinderSimulator` using the current engine settings.

### Recording Audio
1. During a transient pipe simulation (scope view), enable the **Record Audio** toggle on the toolbar (if present in your build).
2. Each simulation step appends the tailpipe pressure sample via `AudioSynthesizer.add_sample`.
3. Click **Save WAV** to export the buffered signal; pressure is resampled to 44.1 kHz, filtered, normalized, and written as a `.wav` file.

### Saving/Loading JSON Configurations
- **Save:** Use the toolbar save icon or File → Save to write the current `Engine` configuration to JSON via `Engine.save_to_file`.
- **Load:** Use File → Load to restore an existing configuration; the tree and property editors refresh automatically.

### Running Optimization Sweeps
1. Open the **Optimizer** tab.
2. Choose a target parameter (e.g., intake runner length, cam intake duration, compression ratio) and set start/end/step values.
3. Click **Run Optimization Sweep**. The optimizer temporarily adjusts the selected parameter, runs dyno simulations over the RPM range, records peak horsepower, updates a progress bar, and plots Parameter Value vs. Peak HP.
4. When finished, the original engine settings are restored automatically, so you can adopt the best value manually.

### Notes on Physics Models
- **Gas Dynamics:** Pipes advance with a Lax–Wendroff finite-volume scheme, ghost cells for boundary reflection, transmissive outlets, and stability clamps (density/energy, CFL timestep).
- **Valve Flow:** Mass transfer uses isentropic relations with choking detection and discharge coefficients.
- **Thermo Cycle:** Cylinder pressure uses phase-aware intake/compression/combustion/exhaust masks with Wiebe heat release and friction torque subtraction for brake output.
- **Audio:** Raw pressure histories are interpolated to fixed-rate audio with optional DC removal to hear exhaust timbre.
