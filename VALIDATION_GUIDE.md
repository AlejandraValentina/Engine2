# VALIDATION_GUIDE.md

Esta guía resume cómo validar PyWaveDyn sin depender de la GUI, usando solo comandos reproducibles.

## Niveles de validación
1. **Smoke (GUI):** `python main.py` (abre la aplicación; valida que arranque sin errores).
2. **Unit:** `python -m pytest tests/unit`.
3. **Integration (opt-in):** `python -m pytest tests/integration` o casos marcados `-m integration`.
4. **Contratos 0D/1D:** `python -m pytest -q tests/test_contract_*.py`.
5. **Identidades/Tendencias/Sanidad:**
   - Identidades: `python -m pytest -q tests/test_identities.py`
   - Tendencias: `python -m pytest -q tests/test_trends.py`
   - Bandas de sanidad: `python -m pytest -q tests/test_sanity_bands.py`
6. **Presets y script físico:** `python validate_physics.py` (usa presets como K20/V8/F1 si el entorno tiene dependencias instaladas).

## Instalación de dependencias
- Base: `python -m pip install -r requirements.txt`
- Desarrollo y pruebas: `python -m pip install -r requirements-dev.txt`

## Expectativas mínimas
- **0D (thermo):** `CylinderSimulator.run_cycle` devuelve diccionario con torque/potencia/bmep/VE/knock finitos y no negativos (torque/potencia), sin NaN/inf.
- **1D (simulator):** Las condiciones de borde construyen estados fantasmas con presión ambiente y densidad/energía positivas; el estado `U` se mantiene finito tras aplicar el outlet.

## Definición de “implementado”
Un feature se considera implementado cuando existe un comando reproducible y/o un test verde que lo cubre. Las features marcadas como futuras en `FEATURES.md` requieren un test o comando adicional antes de considerarse completas.
