# Guía de Validación (PyWaveDyn)

## Cómo ejecutar las pruebas
- Todo el paquete: `python -m pytest`
- Solo contratos rápidos: `python -m pytest -q tests/test_contract_*.py`
- Solo integración/marcas opcionales: `python -m pytest -m integration`

## Salidas esperadas
- **0D**: `CylinderSimulator.run_cycle` devuelve dict con torque/potencia/bmep/VE/knock sin NaN/inf. Potencia y torque deben ser no negativos y BMEP en bar (absoluta).
- **1D**: BC de escape fija presión ambiente en celda fantasma y conserva densidad/energía positivas; el estado `U` se mantiene finito tras aplicar `_tail_atmosphere`.

## Definición de "implementado"
Un feature se considera implementado cuando:
1. Existe al menos un test verde que lo cubre **o** un comando reproducible documentado.
2. No depende de interacción manual con GUI para validación básica.

## Reproducibilidad
- Usa Python 3.10+.
- Ejecuta desde la raíz del repo con el entorno configurado (`pip install -r requirements-dev.txt`).
- Las pruebas no requieren GUI.
