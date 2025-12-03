# PyWaveDyn Technical Design Document (v1.0)

## System Overview
PyWaveDyn is a 1D gas-dynamics and 0D thermodynamics simulator for internal combustion engines. It follows a light MVC pattern:
- **GUI (PySide6 / pyqtgraph)**: Project explorer and editors drive engine configuration; dyno, analysis, optimizer, and wave scope tabs visualize results.
- **Data Model (JSON-serializable dataclasses)**: `core/engine_components.py` defines all physical components and simulation settings; configs load/save directly to JSON presets.
- **Physics Core**: 
  - **0D Thermo (`core/thermo.py`)** computes in-cylinder pressure/torque via phased four-stroke masks, Wiebe combustion, Woschni heat transfer, friction, knock, and dynamic VE.
  - **1D Wave Action (`core/simulator.py`, `core/numerics.py`, `core/junctions.py`)** solves Euler equations with Lax–Wendroff, ghost cells, and junction mass/energy balance for exhaust/intake piping.
- **Audio (`acoustics/audio_generator.py`)**: Resamples pipe outlet pressure to WAV, mixing cylinders by firing order.

## Physics Model Explained
### 0D Thermodynamics
- **Four-Stroke Phasing**: Angle masks (intake < IVC, compression IVC–360°, power 360°–EVO, exhaust ≥ EVO) derived from cam durations/centers/firing order. Prevents negative torque by keeping phase masks non-empty.
- **Combustion (Wiebe)**: Cumulative burn fraction from Wiebe function; start angle = (360 – ignition advance), duration = configurable. Heat release uses fuel LHV and combustion efficiency, minus Woschni wall losses.
- **Heat Transfer (Woschni)**: Dynamic wall area (head+piston+liner), gas temperature/velocity produce heat-loss term; scaled by bore/heat-loss factors in `SimulationSettings` for calibration.
- **Volumetric Efficiency**: Base VE shaped by cam peak RPM and duration; Mach-index choking with head Mach tolerance and port flow efficiency; pipe tuning and friction factors adjust VE; tuning sensitivity configurable in `SimulationSettings`.
- **Friction (FMEP)**: Chen–Flynn style mean effective pressure `FMEP = A + B·RPM + C·RPM²`, using per-engine coefficients plus global friction scaling; accessory losses added separately.
- **Knock Detection**: Dynamic compression vs fuel octane (and combustion settings) triggers knock flag; dyno UI highlights warnings.

### 1D Wave Action
- **Finite Volume / Lax–Wendroff (`core/numerics.py`)**: JIT-optimized flux computation with geometric area and friction sources; boundary cells restored per step to retain imposed BCs.
- **Ghost Cells & Boundaries**: Reflective (closed valve), transmissive (outlet), and valve-coupled inlet ghost cells drive wave generation without numerical trapping.
- **Junction Handling (`core/junctions.py`)**: Collector volumes conserve mass/energy between primaries and tailpipes, updating pressure/temperature via ideal gas law.
- **Network Solver (`Engine1DSolver`)**: Builds primaries (per-cylinder), collector, and tailpipe; phases cylinder blowdown by firing order and steps all pipes under CFL control.

## Configuration Reference
Each parameter lives in `core/engine_components.py` and is editable in the GUI. Typical ranges are guidance, not limits.

### Block
- **bore, stroke (mm)**: Cylinder geometry; higher bore increases area (VE, heat loss). Typical: 70–100 mm (auto), 50–60 mm (small engines).
- **conrod_length (mm)**: Affects slider-crank geometry; typical 120–160 mm (I4), scaled for small engines.
- **num_cylinders, config, bank_angle, firing_order**: Layout and phasing; firing order drives wave timing.
- **redline_rpm**: Dyno sweep upper bound.

### CylinderHead
- **compression_ratio**: Geometric CR; if `combustion_chamber_vol` is set, CR is derived from it. Typical 9–12 (NA street), 12–14 (race).
- **combustion_chamber_vol (cc)**: Fixed clearance override; set to 0 or clear via UI to use CR-derived clearance.
- **intake/exhaust_valves (count)**: Valve count per cylinder.
- **intake_valve_diameter_mm / exhaust_valve_diameter_mm**: Valve sizes; larger diameter reduces Mach index, delays choking. Typical 28–38 mm (I4), 45–52 mm (V8).
- **port_flow_efficiency**: Multiplies effective valve area (Cd). Physics: lower values raise gas velocity, increase choking, reduce VE. Typical 0.55 (economy), 0.65–0.75 (street), 0.85–0.9 (race).
- **mach_tolerance**: Mach index threshold for choking onset. Typical 0.65 (economy), 0.7–0.8 (street), 0.85–0.9 (race).

### Camshaft
- **intake/exhaust_lift (mm)**: Max valve lift; higher lift increases area at peak.
- **intake/exhaust_duration (deg)**: Seat-to-seat duration; longer duration shifts VE peak upward.
- **lobe_separation (deg)**: Separation between intake/exhaust centerlines; tighter LSA increases overlap.
- **advance (deg)**: Installation advance; positive advances intake centerline.
- **peak_rpm**: RPM of peak VE for the cam profile; shapes VE curve.

### IntakeSystem
- **runner_length/diameter (mm)**: Tuning length/area; affects wave tuning and pipe friction. Small diameters increase velocity and friction losses; long runners favor low RPM torque.
- **plenum_volume (L)**: Intake plenum size; larger smooths pulses.
- **throttle_body_dia (mm), throttle_cfm**: Flow limit at high RPM; lower values restrict VE.
- **flow_loss_coefficient**: Additional restriction factor for modeling throttles/filters; higher increases losses.

### ExhaustSystem
- **header_primary_length/diameter (mm)**: Primary tuning; length influences wave timing, diameter impacts friction and Mach index.
- **collector_length (mm)**: Tailpipe length after merge; adjusts tuning.

### Supercharger
- **type**: NA/Turbo/Roots, controls boost usage.
- **boost_pressure_bar**: Added manifold pressure. Higher boost increases trapped mass; check knock limits.
- **intercooler_efficiency**: Fractional temperature drop after compression (0–1). Higher reduces charge temperature/knock.

### Combustion
- **thermal_efficiency**: Fraction of chemical energy converted to pressure (before wall losses). Typical 0.45–0.55 street, up to ~0.62 race.
- **burn_duration (deg)**: Wiebe duration; shorter for fast-burn modern chambers (35–55°).
- **ignition_advance (deg BTDC)**: Start of combustion relative to TDC firing.
- **afr**: Air–fuel ratio; affects fuel mass and mixture.
- **wiebe_a / wiebe_m**: Shape parameters for the Wiebe curve; tune completeness (a) and form (m) for different fuels (e.g., methanol slower burn ⇒ adjust m).
- **chamber_type (preset)**: GUI preset that fills efficiency/burn/advance; set to Custom when manually editing.

### Friction
- **friction_base_kpa / friction_linear_factor / friction_quadratic_factor**: Chen–Flynn FMEP coefficients (A/B/C). Increase C for high-RPM loss.
- **global_scaling_factor**: Master multiplier for friction. Example: 0.6–0.8 small motorcycle engines; 1.0 baseline; >1.0 for heavy-duty engines.
- **accessories (water pump, alternator, PS, fan)**: Adds torque drag at all RPMs.

### SimulationSettings (Environment & Calibration)
- **air_temperature_c / air_pressure_bar**: Ambient conditions for density (altitude/temperature effects).
- **heat_loss_factor**: Multiplies Woschni heat transfer; raise to increase wall losses, lower for insulated engines.
- **pipe_friction_factor**: Scales L/D pipe drag; increase to penalize restrictive exhaust/intake, decrease for polished systems.
- **tuning_sensitivity**: Scales resonance boost; raise for highly tuned systems, lower to damp tuning.

### Fuel
- **type_name, octane_rating**: Octane used for knock comparison.
- **energy_density (J/kg), stoich_afr**: Fuel properties used for heat release and mixture.

## Tuning Guide
- **Simulate a Racing Engine (e.g., F1/V10)**:
  - Head: `port_flow_efficiency` ~0.85–0.9, `mach_tolerance` ~0.9.
  - Cam: High `peak_rpm`, long durations, moderate LSA; high `advance` for overlap.
  - Friction: Lower `global_scaling_factor` (0.7–0.85) and lighter accessory set.
  - Combustion: Higher `thermal_efficiency` (0.58–0.62), shorter `burn_duration`, aggressive `ignition_advance`.
  - SimulationSettings: Lower `heat_loss_factor` if modeling advanced cooling; higher `tuning_sensitivity`.

- **Simulate a Small Engine (e.g., 125–250cc)**:
  - Friction: Reduce `global_scaling_factor` (0.6–0.8) to avoid automotive FMEP assumptions.
  - Head: Modest `port_flow_efficiency` (~0.55–0.65), `mach_tolerance` ~0.65–0.75.
  - Combustion: Moderate `thermal_efficiency` (0.45–0.52), longer `burn_duration`.
  - SimulationSettings: Increase `heat_loss_factor` slightly for air-cooled engines; reduce `tuning_sensitivity` for less resonance.

- **Reduce Knock at High CR/Boost**:
  - Lower `ignition_advance`, `compression_ratio`, or `boost_pressure_bar`.
  - Improve charge cooling: raise `intercooler_efficiency`, lower `air_temperature_c`.
  - Use higher `octane_rating` fuel.

## File Structure
- **core/engine_components.py**: Dataclasses for all components (Block, Head, Camshaft, Intake/Exhaust, Supercharger, Combustion, Friction, SimulationSettings, Fuel, Engine container).
- **core/thermo.py**: 0D cycle simulator (Wiebe combustion, Woschni heat transfer, VE, friction, knock, torque/power outputs).
- **core/numerics.py**: Numba-jitted Euler fluxes, Lax–Wendroff step, valve mass flow.
- **core/junctions.py**: 0D junction mass/energy balance for collectors.
- **core/simulator.py**: Engine1DSolver network (primaries/collector/tailpipe) built from engine config.
- **gui/main_window.py**: PySide6 UI, property editors, dyno/optimizer/analysis, wave scope, fabrication tools.
- **gui/widgets/scope_widget.py**: Plotting helpers for wave visualization.
- **acoustics/audio_generator.py**: Audio resampling and multi-cylinder mixing.
- **tests/**: Unit, integration, and sanity-band validations; fixtures in `tests/conftest.py`.
- ***.json** presets: Example engines (Honda K20, Chevy V8, Ferrari V12, etc.).

## Cleanup Notes
Temporary scripts superseded by the integrated UI and test suite should be removed (e.g., legacy `test_solver.py`, ad-hoc validation scripts). The current tree relies on the formal pytest suite and GUI workflows.
