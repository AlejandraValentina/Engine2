# PyWaveDyn — Checklist de Features

**Status:** `Implemented` | `Partial` | `Planned` (this file is the single source of truth; implemented items require runnable evidence).


## Release v2.0 scope
Ver `docs/RELEASE_V2_SCOPE.md` (unico scope congelado v2.0).

## Release v2.1 scope
Ver `docs/RELEASE_V2_1_SCOPE.md` (unico scope congelado v2.1).

## Release v2.2 scope
Ver `docs/RELEASE_V2_2_SCOPE.md` (unico scope congelado v2.2).

## Release v2.2 scope (FULL-NETWORK + BENCHMARKS + RESIDUAL-COMBUSTION + OPTIMIZE + PERFORMANCE)
- [x] Full multi-cilindro 1D network intake+exhaust + CLI + schema — Evidencia: `core/full_network.py`, `pywavedyn/cli.py`, `schemas/full_scope.schema.json`, `tests/test_network_build_smoke.py`, `tests/integration/test_full_network_cross_talk_plenum.py`, `tests/integration/test_full_network_runner_length_shifts_torque_peak.py`, `tests/test_output_schema_full_scope.py`. Run: `python -m pywavedyn.cli full-scope --engine presets/legacy/custom_twin_230cc.json --duration 0.02 --target-dx 0.05 --max-steps 200 --out full_scope.json`.
- [x] Benchmarks externos (2 presets) + selfcheck + schema — Evidencia: `presets/benchmark_mono_na.json`, `presets/benchmark_turbo_small.json`, `validation_cases/benchmark_mono_na.json`, `validation_cases/benchmark_turbo_small.json`, `tests/test_selfcheck_schema_validates.py`, `tests/integration/test_new_presets_smoke.py`. Run: `python -m pywavedyn.cli selfcheck --expectations validation_cases/expectations.json --out selfcheck_report.json`.
- [x] Residuals→combustión opt-in — Evidencia: `core/thermo.py`, `tests/test_residual_combustion_coupling_noop_when_disabled.py`, `tests/integration/test_residuals_reduce_power_at_high_overlap_trend.py`. Run: `python -m pytest -q tests/test_residual_combustion_coupling_noop_when_disabled.py` (+ integration: `python -m pytest -m integration -q tests/integration/test_residuals_reduce_power_at_high_overlap_trend.py`).
- [x] Optimize runner determinista + schema — Evidencia: `core/optimize_runner.py`, `pywavedyn/cli.py`, `schemas/opt_report.schema.json`, `tests/test_optimize_deterministic_same_seed_same_result.py`, `tests/integration/test_optimize_reduces_error.py`, `tests/test_output_schema_opt_report.py`. Run: `python -m pywavedyn.cli optimize --engine presets/legacy/custom_twin_230cc.json --target target.json --param intake.runner_length --bounds 0.20,0.60 --seed 123 --max-evals 30 --out opt_report.json`.
- [x] Performance contracts (max_steps + fast-numba parity) — Evidencia: `tests/test_max_steps_enforced_no_hang.py`, `tests/perf/test_fast_path_parity_small_case.py`, `pywavedyn/cli.py`. Run: `python -m pytest -q tests/test_max_steps_enforced_no_hang.py` (+ perf: `python -m pytest -m perf -q tests/perf/test_fast_path_parity_small_case.py`).

## Release v2.1 scope (INTAKE+SCAVENGING+MAP+THERMAL+CALIBRATION)
- [x] Intake 1D headless (plenum -> runner -> valvula) + CLI + schema — Evidencia: `core/intake_scope.py`, `pywavedyn/cli.py`, `schemas/intake_scope.schema.json`, `tests/test_intake_scope_smoke.py`, `tests/test_output_schema_intake_scope.py`. Run: `python -m pywavedyn.cli intake-scope --engine presets/legacy/custom_twin_230cc.json --target-dx 0.05 --max-steps 30 --out intake_scope.json`.
- [x] Acople 0D<->1D en admision + scavenging/overlap (opt-in) — Evidencia: `core/intake_coupling.py`, `core/thermo.py`, `tests/test_intake_coupling_noop_when_disabled.py`, `tests/test_scavenging_metrics_present_when_enabled.py`, `tests/integration/test_intake_coupling_affects_map_ve.py`. Run: `python -m pytest -q tests/test_intake_coupling_noop_when_disabled.py tests/test_scavenging_metrics_present_when_enabled.py` (+ integration: `python -m pytest -m integration -q tests/integration/test_intake_coupling_affects_map_ve.py`).
- [x] Part-load map runner headless + schema — Evidencia: `core/map_runner.py`, `pywavedyn/cli.py`, `schemas/map.schema.json`, `tests/test_headless_partload_map_generates_grid.py`, `tests/test_output_schema_map.py`. Run: `python -m pywavedyn.cli map --engine presets/legacy/custom_twin_230cc.json --rpm-grid 2000,3000 --throttle-grid 0.4,1.0 --out map.json`.
- [x] Modelo termico opt-in (pared lumped) + gas thermally-perfect opt-in — Evidencia: `core/advanced/wall_thermal.py`, `core/thermo.py`, `tests/test_thermally_perfect_properties_sane.py`, `tests/integration/test_wall_thermal_reduces_egt_trend.py`. Run: `python -m pytest -q tests/test_thermally_perfect_properties_sane.py` (+ integration: `python -m pytest -m integration -q tests/integration/test_wall_thermal_reduces_egt_trend.py`).
- [x] Auto-calibracion opt-in contra curva objetivo + schema — Evidencia: `core/auto_calibration.py`, `pywavedyn/cli.py`, `schemas/calib_report.schema.json`, `tests/integration/test_autocalibration_reduces_error.py`, `tests/test_output_schema_calib_report.py`. Run: `python -m pywavedyn.cli calibrate --engine presets/legacy/custom_twin_230cc.json --target target.json --out calib_report.json --max-evals 40 --params ve_scale,friction_scale,burn_scale`.

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
