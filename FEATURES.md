# PyWaveDyn — Checklist de Features

**Status:** `Implemented` | `Partial` | `Planned` (this file is the single source of truth; implemented items require runnable evidence).


## Release v2.0 scope
Ver `docs/RELEASE_V2_SCOPE.md` (unico scope congelado v2.0).

## Release v2.1 scope
Ver `docs/RELEASE_V2_1_SCOPE.md` (unico scope congelado v2.1).

## 1) Dyno 0D (thermo)
- [x] Virtual dyno 0D (Otto con Wiebe/Woschni, knock, FMEP) — Evidencia: `core/thermo.py`, presets canónicos en `presets/` (`honda_k20.json`, `chevy_350.json`, `ferrari_f1.json`), contratos en `tests/test_contract_0d.py`, identidades/trends/sanity en `tests/test_identities.py`, `tests/test_trends.py`, `tests/test_sanity_bands.py`. Run: `python -m pytest -q tests/test_contract_0d.py`.

## 2) Wave Scope 1D (simulator/numerics)
- [x] Solver 1D de escape (Euler + Lax–Wendroff + celdas fantasma + colector) — Evidencia: `core/simulator.py`, `core/numerics.py`, `gui/widgets/scope_widget.py`. Run: `python -m pytest -m integration -q tests/test_contract_1d_bc.py`.
- [x] Área real de válvula (cortina + Cd) en 1D — Evidencia: `core/simulator.py`, `tests/test_valve_area_curtain.py`. Run: `python -m pytest -q tests/test_valve_area_curtain.py`.
- [x] Acople 0D→1D unidireccional (escape) — Evidencia: `tests/integration/test_0d_to_1d_scope.py` (marcado integration). Run: `python -m pytest -m integration -q tests/integration/test_0d_to_1d_scope.py`.
- [x] Acople 0D→1D bidireccional — Evidencia: `tests/integration/test_0d_1d_bidirectional_backpressure_affects_cycle.py` (marcado integration). Run: `python -m pytest -m integration -q tests/integration/test_0d_1d_bidirectional_backpressure_affects_cycle.py`.

## 3) Audio (acoustics)
- [x] Síntesis multi-cilindro verificada — Evidencia: `tests/test_audio_multicyl_wav_nonempty.py`. Run: `python -m pytest -q tests/test_audio_multicyl_wav_nonempty.py`.

## 4) Optimización
- [x] Barridos automáticos sin GUI — Evidencia: `tests/test_headless_sweep_runner_length.py`. Run: `python -m pytest -q tests/test_headless_sweep_runner_length.py`.

## 5) Fabricación
- [x] Reporte/cut-list reproducible por CLI — Evidencia: `tests/test_cutlist_cli_generates_expected_keys.py`. Run: `python -m pytest -q tests/test_cutlist_cli_generates_expected_keys.py`.

## 6) QA / Validación
- [x] Identidades físicas y bandas de sanidad — Evidencia: `tests/test_identities.py`, `tests/test_sanity_bands.py`. Run: `python -m pytest -q tests/test_identities.py tests/test_sanity_bands.py`.
- [x] Tendencias verificables (boost, restricciones, fricción) — Evidencia: `tests/test_trends.py`. Run: `python -m pytest -q tests/test_trends.py`.
- [x] Contratos básicos 0D/1D — Evidencia: `tests/test_contract_0d.py`, `tests/test_contract_1d_bc.py` (integration). Run: `python -m pytest -q tests/test_contract_0d.py` (y opt-in `python -m pytest -m integration -q tests/test_contract_1d_bc.py`).
- [x] Presets legacy movidos a `presets/legacy/` — Evidencia: `AUDIT_REPORT.md`.
- [x] Cobertura de regresión para presets legacy — Evidencia: `tests/legacy/test_legacy_presets_load_and_run_0d.py` (marker `legacy`). Run: `python -m pytest -q -m legacy`.

## 7) CLI Headless
- [x] CLI dyno/scope reproducible — Evidencia: `pywavedyn/cli.py`, `tests/test_cli_outputs.py`. Run: `python -m pytest -q tests/test_cli_outputs.py`.

## 8) Selfcheck & Validation Cases
- [x] Selfcheck gate con dataset mínimo — Evidencia: `validation_cases/`, `pywavedyn/cli.py`, `tests/test_selfcheck_cli.py`. Run: `python -m pywavedyn.cli selfcheck --expectations validation_cases/expectations.json --out selfcheck_report.json`.

## 9) Advanced Physics Core (v2)
- [x] Pro Dyno v2 (advanced sweep runner) - Evidencia: `core/pro_dyno_v2.py`, `gui/main_window.py`, `tests/test_pro_dyno_v2.py`. Run: `python -m pytest -q tests/test_pro_dyno_v2.py`.
- [x] Coupled 0D-1D core (advanced path, opt-in) - Evidencia: `core/advanced/orchestrator.py`, `tests/test_pro_dyno_v2.py`, `tests/unit/test_orchestrator_uses_pipe_pressure_as_nozzle_downstream.py`, `tests/unit/test_orchestrator_ghost_uses_upstream_totals_on_backflow.py`. Run: `python -m pytest -q tests/test_pro_dyno_v2.py tests/unit/test_orchestrator_uses_pipe_pressure_as_nozzle_downstream.py tests/unit/test_orchestrator_ghost_uses_upstream_totals_on_backflow.py`.
- [x] v2 unit tests (nozzle/CFL/passive scalar/roundtrip) - Evidencia: `tests/unit/test_nozzle_direction_uses_stagnation_when_available.py`, `tests/unit/test_cfl_ignores_ghost_left_extremes.py`, `tests/unit/test_solver1d_rhoY_consistent_after_density_floor.py`, `tests/unit/test_state_conversions.py`. Run: `python -m pytest -q tests/unit/test_nozzle_direction_uses_stagnation_when_available.py tests/unit/test_cfl_ignores_ghost_left_extremes.py tests/unit/test_solver1d_rhoY_consistent_after_density_floor.py tests/unit/test_state_conversions.py`.
- [x] v2 integration tests (ram charging / blowdown) - Evidencia: `tests/integration/test_ram_charging.py`, `tests/integration/test_blowdown_wave_time.py`. Run: `python -m pytest -q tests/integration/test_ram_charging.py tests/integration/test_blowdown_wave_time.py`.
- [x] 1D SoA + Numba kernel (opt-in) - Evidencia: `tests/unit/test_solver1d_numba_matches_python_step.py`, `tests/unit/test_solver1d_numba_respects_guardrails_no_warnings.py`, `tests/unit/test_solver1d_soa_matches_aos_step.py`. Run: `python -m pytest -q tests/unit/test_solver1d_numba_matches_python_step.py tests/unit/test_solver1d_numba_respects_guardrails_no_warnings.py tests/unit/test_solver1d_soa_matches_aos_step.py`.
- [x] Junction mixing + per-leg losses (opt-in) - Evidencia: `core/advanced/junctions.py`, `tests/unit/test_junction_mixing.py`, `tests/unit/test_junction_leg_k_manual_reduces_mdot_no_flip.py`, `tests/unit/test_estimate_K_from_geometry_monotonic.py`. Run: `python -m pytest -q tests/unit/test_junction_mixing.py tests/unit/test_junction_leg_k_manual_reduces_mdot_no_flip.py tests/unit/test_estimate_K_from_geometry_monotonic.py`.
- [x] Cylinder heat transfer (opt-in) - Evidencia: `core/advanced/cylinder_cv.py`, `tests/unit/test_cylinder_heat_transfer.py`. Run: `python -m pytest -q tests/unit/test_cylinder_heat_transfer.py`.
- [x] Under-relaxation for coupling totals (opt-in) - Evidencia: `tests/unit/test_coupling_under_relaxation.py`. Run: `python -m pytest -q tests/unit/test_coupling_under_relaxation.py`.
- [x] Convergence history export (advanced) - Evidencia: `tests/unit/test_convergence_history_export.py`. Run: `python -m pytest -q tests/unit/test_convergence_history_export.py`.
- [x] Throttle (opt-in) + rate limiting + safety clamps - Evidencia: `tests/unit/test_throttle_boundary.py`, `tests/unit/test_throttle_rate_limit.py`.
- [x] Pipe prefill (opt-in) + auto defaults (opt-in) - Evidencia: `tests/unit/test_pipe_prefill.py`, `tests/unit/test_pipe_prefill_auto_defaults.py`.
- [x] Valve-closed wall BC (opt-in) - Evidencia: `tests/unit/test_valve_closed_wall_bc.py`.
- [x] NASA7 cp_model="nasa7" (opt-in) - Evidencia: `tests/unit/test_nasa7_thermo.py`.
- [x] Fuel/BSFC accounting (opt-in) - Evidencia: `tests/unit/test_fuel_lambda_mode_basic.py`, `tests/unit/test_fuel_disabled_no_outputs.py`, `tests/unit/test_bsfc_formula_g_per_kwh.py`, `tests/unit/test_sweep_records_fuel_metrics.py`.
- [x] Part-load sweep outputs + pumping work (opt-in) - Evidencia: `tests/unit/test_throttle_part_load_monotonic.py`, `tests/unit/test_bsfc_part_throttle_increases.py`, `tests/unit/test_sweep_produces_monotonic_rpm_grid.py`.
- [x] Intake plenum CV (opt-in) - Evidencia: `tests/unit/test_plenum_capacitance_damps_map.py`, `tests/unit/test_plenum_defaults_no_change.py`, `tests/unit/test_plenum_mass_scalar_invariants.py`.
- [x] Exhaust plenum CV (opt-in) - Evidencia: `tests/unit/test_exhaust_plenum_damps_blowdown_peak.py`, `tests/unit/test_exhaust_plenum_defaults_no_change.py`, `tests/unit/test_exhaust_plenum_mass_scalar_invariants.py`.
- [x] Junction capacitance v2 reservoir + per-leg K-loss hooks (opt-in) - Evidencia: `tests/unit/test_junction_capacitance.py`, `tests/unit/test_junction_capacitance_conserves_mass_scalar.py`, `tests/unit/test_junction_leg_k_loss_reduces_mdot_bidirectional.py`, `tests/unit/test_junction_leg_k_manual_reduces_mdot_no_flip.py`.
- [x] Junction capacitance wired into network runner path (opt-in) - Evidencia: `tests/unit/test_network_runner_junction_capacitance_wiring.py`.
