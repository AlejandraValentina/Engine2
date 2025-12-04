# PyWaveDyn — Checklist de Features

## 1) Core 0D Dyno
- [x] Simulación 0D de ciclo Otto con Wiebe/Woschni: evidencias en `tests/test_contract_0d.py` y suite de tendencias/sanity (`tests/test_trends.py`, `tests/test_sanity_bands.py`).

## 2) 1D Exhaust Wave Solver
- [x] Solver 1D de ondas en escape (Euler + Lax–Wendroff + celdas fantasma): contrato de BC en `tests/test_contract_1d_bc.py` (marcado como integration).
- [ ] Acople completo 0D→1D bidireccional: criterio futuro: test de integración que compare backpressure dinámica vs. heurística.

## 3) Audio
- [ ] Síntesis multi-cilindro exportable desde CLI/GUI: criterio futuro: test que verifique generación de WAV no vacío al mezclar firing order.

## 4) Optimización
- [ ] Barridos automáticos sin GUI: criterio futuro: test headless que ejecute un sweep de un parámetro y genere curva de potencia.

## 5) Fabricación
- [ ] Reporte/cut-list reproducible por CLI: criterio futuro: comando/documento que produzca el listado desde presets sin GUI.

## 6) Validación / QA
- [x] Identidades físicas y bandas de sanidad: `tests/test_identities.py`, `tests/test_sanity_bands.py`, `tests/test_contract_0d.py`.
- [x] Tendencias verificables (boost, restricciones, fricción): `tests/test_trends.py`.
