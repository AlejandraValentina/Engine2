# GUI Overview (PySide6)

This document inventories the current GUI surface area and maps each action to the underlying core/CLI implementation. The CLI + tests remain the source of truth for behavior and schemas.

## Tabs and Views

### Overview
- **Purpose:** Read-only summary of the current `Engine` object.
- **Backing:** `gui/main_window.py::update_overview` (reads `Engine` and component fields).
- **Status:** Supported (core data is validated by unit tests).

### Properties
- **Purpose:** Edit component values (Block, Head, Camshaft, Intake, Exhaust, SimulationSettings, etc.).
- **Backing:** `gui/main_window.py` property editor bindings using `Engine` dataclasses.
- **Status:** Supported (same fields as core dataclasses).

### Quick Dyno (Dyno Graph)
- **Purpose:** Run power/torque sweep and plot results.
- **Mode v1 (Quick 0D):** `core/thermo.CylinderSimulator` (same as CLI dyno v1).
- **Mode v2 (Pro Coupled):** `core/pro_dyno_v2.ProDynoV2Runner` (same as CLI dyno v2).
- **Export Dyno JSON:** Writes CLI-compatible dyno output (`schemas/dyno.schema.json`) using the same metadata+results structure.
- **Status:** Supported; aligns with CLI runners.

### Analysis
- **Purpose:** Tabular breakdown of v1 dyno results (power/torque/BMEP/VE/airflow, etc.).
- **Backing:** `gui/main_window.py::update_analysis_table` based on `CylinderSimulator` outputs.
- **Status:** v1-only (v2 provides aggregate sweep data in Quick Dyno/Pro Dyno tabs).

### Pro Dyno
- **Purpose:** Run v2 coupled sweep with convergence plots.
- **Backing:** `core/pro_dyno_v2.ProDynoV2Runner` + convergence history.
- **Status:** Supported; validation in v2 unit/integration tests.

### Wave Sim
- **Purpose:** Exhaust wave scope visualization and audio capture.
- **Backing:** `core.simulator.Engine1DSolver`, `core.wave_utils`, `acoustics.audio_generator`.
- **Status:** Supported; aligns with CLI scope and audio paths.

### Fabrication
- **Purpose:** Heuristic fabrication table and cut-list report.
- **Backing:** `gui/main_window.py` (no CLI equivalent).
- **Status:** Prototype UI convenience (not validated by CLI/tests).

## File/Project Actions
- **File → Load/Save:** `Engine.from_dict` / `Engine.save_to_file` (schema-backed).
- **Export Dyno JSON:** CLI-compatible output validated against `schemas/dyno.schema.json`.

## Notes
- GUI features must reuse core runners; no simulator defaults are changed by the GUI.
- When a configuration option is not exposed in the GUI, it is preserved on load/save and can be edited in JSON or via CLI.
