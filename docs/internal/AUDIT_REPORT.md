# AUDIT_REPORT

## Presets
- **Canónicos**
  - `presets/honda_k20.json` (schema_version=1, model_name="Honda K20 Inline-4") — benchmark L4.
  - `presets/chevy_350.json` (schema_version=1, model_name="Chevy 350 V8") — benchmark V8 calle.
  - `presets/ferrari_f1.json` (schema_version=1, model_name="Ferrari F1 V12") — benchmark alta RPM.
- **Legacy**
  - `presets/legacy/custom_twin_230cc.json` — esquema antiguo/pequeño desplazamiento.
  - `presets/legacy/ferrari_355_v12.json` — preset previo no canónico.
  - `presets/legacy/chevy_350_legacy.json` — legado v1 para regresión.

## Legacy compatibility mode
- Perfil `legacy_compat v1` (opt-in): fuerza flags v1.0 (cp_model constante, heat transfer 1D off, wall thermal off, residuals advanced off, shock_cfl off).
- Auto-legacy para presets bajo `presets/legacy` con `--auto-legacy-compat`.
- Regresión golden: `benchmarks/datasets/regression_golden/legacy_compat/*.json`.

## Validation Cases
- `validation_cases/k20_like.json`, `validation_cases/v8_like.json`, `validation_cases/single_cyl_moto_like.json`
- `validation_cases/throttle_part_load_k20_like.json`, `validation_cases/intake_plenum_effect.json`, `validation_cases/wall_thermal_effect.json`
- `validation_cases/scope_tube_pulse.json`, `validation_cases/scope_simple_header.json`
- Expectativas: `validation_cases/expectations.json` (usado por `pywavedyn.cli selfcheck`).

## Benchmarks datasets
- `benchmarks/datasets/honda_k20_na/` (reference toy)
- `benchmarks/datasets/custom_twin_230cc/` (reference toy)
- `benchmarks/datasets/chevy_350_na/` (regression_golden)
- `benchmarks/datasets/ferrari_f1_na/` (regression_golden)
- `benchmarks/datasets/single_cyl_moto_na/` (regression_golden)
- `benchmarks/datasets/k20_like_regression_golden/` (regression_golden)
- `benchmarks/datasets/v8_like_regression_golden/` (regression_golden)
- `benchmarks/datasets/f1_like_regression_golden/` (regression_golden)
- `benchmarks/datasets/k20_like_real/` (real_data canonical package)
- `benchmarks/datasets/v8_like_real/` (real_data canonical package)
- `benchmarks/datasets/f1_like_real/` (real_data placeholder legacy)

## Tests
- **Unit/contratos (por defecto)**:
  - 0D contratos: `tests/test_contract_0d.py` — Run: `python -m pytest -q tests/test_contract_0d.py`
  - Identidades/sanidad/trends: `tests/test_identities.py`, `tests/test_sanity_bands.py`, `tests/test_trends.py`
  - Núcleo y física: `tests/test_core.py`, `tests/test_physics.py`, `tests/test_engine_suite.py`, `tests/test_tiered_validation.py`
  - 1D unidades/BC: `tests/test_1d_units_and_friction.py`, `tests/test_1d_gas_properties.py`, `tests/test_1d_heat_transfer_disabled.py`
  - Válvula y tobera: `tests/test_valve_area_curtain.py`, `tests/test_valve_area_placeholder.py`, `tests/test_nozzle_choking.py`
  - Acople/flags: `tests/test_coupling_flag.py`, `tests/test_junction_coupling.py`
  - CLI/metadata: `tests/test_cli_outputs.py`
  - Presets/units: `tests/test_preset_consistency.py`, `tests/test_units_contracts.py`, `tests/test_wave_utils.py`, `tests/test_engine_validation_issues.py`
- **Integration (opt-in)**:
  - `tests/integration/test_thermo_k20.py`
  - `tests/integration/test_0d_to_1d_scope.py`
  - `tests/test_contract_1d_bc.py` (marcado integration)
- **System (opt-in)**:
  - CLI end-to-end + schemas: `tests/system/test_all_cli_outputs_validate_schemas.py`
  - Benchmarks regression suites: `tests/system/test_benchmark_*_schema_and_metrics.py`
  - GUI export schema: `tests/system/test_gui_export_dyno_schema.py`
- **Perf/Stress (opt-in)**:
  - `tests/perf/test_fast_path_parity_small_case.py`
  - `tests/stress/test_network_adversarial_no_hang.py` (si aplica)
- **Legacy/Frozen**: marker `legacy` disponible.

## Comandos de validación
- Completo por defecto: `python -m pytest -q`
- Integración (opt-in): `python -m pytest -m integration -q`
- CLI smoke: `python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 2000:3000:500 --out out.json`
