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
- **Unit/contratos (se ejecutan por defecto)**: `tests/test_identities.py`, `tests/test_trends.py`, `tests/test_sanity_bands.py`, `tests/test_core.py`, `tests/test_contract_0d.py`, `tests/test_tiered_validation.py`, `tests/test_engine_suite.py`, `tests/test_physics.py`.
- **Integration (opt-in)**: `tests/integration/test_thermo_k20.py`, `tests/test_contract_1d_bc.py` (BC 1D).
- **Legacy/Frozen**: ninguno movido; usar marker `legacy` si se recuperan pruebas antiguas.

## Comandos de validación
- Completo por defecto: `python -m pytest`
- Integración (opt-in): `python -m pytest -m integration`
