# AUDIT_REPORT

## Presets
- **Canónicos**
  - `presets/honda_k20.json` (schema_version=1, model_name="Honda K20 Inline-4") — benchmark L4.
  - `presets/chevy_350.json` (schema_version=1, model_name="Chevy 350 V8") — benchmark V8 calle.
  - `presets/ferrari_f1.json` (schema_version=1, model_name="Ferrari F1 V12") — benchmark alta RPM.
- **Legacy**
  - `presets/legacy/custom_twin_230cc.json` — esquema antiguo/pequeño desplazamiento.
  - `presets/legacy/ferrari_355_v12.json` — preset previo no canónico.

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
- **Legacy/Frozen**: ninguno actualmente (marker `legacy` disponible).

## Comandos de validación
- Completo por defecto: `python -m pytest -q`
- Integración (opt-in): `python -m pytest -m integration -q`
- CLI smoke: `python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 2000:3000:500 --out out.json`
