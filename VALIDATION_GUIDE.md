# VALIDATION_GUIDE.md

Esta guía resume cómo validar PyWaveDyn sin depender de la GUI, usando solo comandos reproducibles y marcadores de pytest.

## Niveles de validación
1. **Smoke (GUI):** `python main.py` (abre la aplicación; valida arranque).
2. **Unit-like (sin integration/legacy):** `python -m pytest -q -m "not integration and not legacy"`.
3. **Integration (opt-in):** `python -m pytest -m integration` o `python -m pytest tests/integration`.
4. **Contratos 0D/1D:** `python -m pytest -q tests/test_contract_*.py`.
5. **Identidades/Tendencias/Sanidad:**
   - Identidades: `python -m pytest -q tests/test_identities.py`
   - Tendencias: `python -m pytest -q tests/test_trends.py`
   - Bandas de sanidad: `python -m pytest -q tests/test_sanity_bands.py`
6. **CLI headless (dyno/scope):**
   - `python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 2000:4000:500 --out out_dyno.json`
   - `python -m pywavedyn.cli scope --engine presets/honda_k20.json --rpm 2500 --cycles 1 --out out_scope.json`
7. **Presets canónicos:** cargar `presets/honda_k20.json`, `presets/chevy_350.json`, `presets/ferrari_f1.json` en pruebas o herramientas externas según sea necesario.

**Nota sobre presets y CR:** si un preset define `combustion_chamber_vol`, ese valor overridea la geometría implícita al declarar la relación de compresión; mantener `combustion_chamber_vol` coherente con `compression_ratio` (véase `tools/audit_presets.py`).

## Required checks (PR gate)
- **Must pass:** `python -m pytest -q`
- **Optional/CI integration:** `python -m pytest -q -m integration`
- **CLI smoke (metadata):**
  - `python -m pywavedyn.cli dyno --engine presets/honda_k20.json --rpm 2000:2500:500 --out out_dyno.json`
  - `python -m pywavedyn.cli scope --engine presets/honda_k20.json --rpm 2000 --cycles 1 --out out_scope.json`

## Comportamiento de validación en la GUI
- **Carga (non-strict):** al abrir un JSON, `Engine.validate_with_issues()` reúne advertencias. Se muestra un cuadro de aviso pero el proyecto se carga.
- **Guardado (strict):** al guardar, la validación estricta bloquea el guardado si hay errores y muestra el mensaje en la barra de estado y un diálogo.

## Instalación de dependencias
- Base: `python -m pip install -r requirements.txt`
- Desarrollo y pruebas: `python -m pip install -r requirements-dev.txt`

## Expectativas mínimas
- **0D (thermo):** `CylinderSimulator.run_cycle` devuelve diccionario con torque/potencia/bmep/VE/knock finitos y no negativos (torque/potencia), sin NaN/inf.
- **1D (simulator):** Las condiciones de borde construyen estados fantasmas con presión ambiente y densidad/energía positivas; el estado `U` se mantiene finito tras aplicar el outlet (ver `tests/test_contract_1d_bc.py`, marcado integration).
- **Válvula/boquilla:** `tests/test_valve_area_curtain.py` valida que el área de cortina sea monotónica con la alzada; `tests/test_nozzle_choking.py` valida el cambio entre régimen ahogado y no ahogado.
- **Acoplamiento 0D→1D (escape):** `tests/integration/test_0d_to_1d_scope.py` verifica que la presión 1D responda a la apertura real de válvula sin NaN.

## Definición de “implementado”
Un feature se considera implementado cuando existe un comando reproducible y/o un test verde que lo cubre. Las features marcadas como futuras en `FEATURES.md` requieren un test o comando adicional antes de considerarse completas.
