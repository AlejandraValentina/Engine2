# PyWaveDyn — Checklist de Features

## 1) Dyno 0D (thermo)
- [x] Virtual dyno 0D (Otto con Wiebe/Woschni, knock, FMEP) — Evidencia: `core/thermo.py`, presets canónicos en `presets/` (`honda_k20.json`, `chevy_350.json`, `ferrari_f1.json`), contratos en `tests/test_contract_0d.py`, identidades/trends/sanity en `tests/test_identities.py`, `tests/test_trends.py`, `tests/test_sanity_bands.py`. Run: `python -m pytest -q tests/test_contract_0d.py`.

## 2) Wave Scope 1D (simulator/numerics)
- [x] Solver 1D de escape (Euler + Lax–Wendroff + celdas fantasma + colector) — Evidencia: `core/simulator.py`, `core/numerics.py`, `gui/widgets/scope_widget.py`. Run: `python -m pytest -m integration -q tests/test_contract_1d_bc.py`.
- [x] Área real de válvula (cortina + Cd) en 1D — Evidencia: `core/simulator.py`, `tests/test_valve_area_curtain.py`. Run: `python -m pytest -q tests/test_valve_area_curtain.py`.
- [x] Acople 0D→1D unidireccional (escape) — Evidencia: `tests/integration/test_0d_to_1d_scope.py` (marcado integration). Run: `python -m pytest -m integration -q tests/integration/test_0d_to_1d_scope.py`.
- [ ] Acople 0D→1D bidireccional — Criterio de aceptación: test de integración que compare backpressure dinámica del 1D con la heurística 0D y afecte el ciclo.

## 3) Audio (acoustics)
- [ ] Síntesis multi-cilindro verificada — Criterio de aceptación: comando o test que genere un WAV no vacío mezclando firing order desde `acoustics/audio_generator.py` sin depender de GUI.

## 4) Optimización
- [ ] Barridos automáticos sin GUI — Criterio de aceptación: test headless que ejecute un sweep (p. ej., runner length) y produzca curva de potencia/HP.

## 5) Fabricación
- [ ] Reporte/cut-list reproducible por CLI — Criterio de aceptación: comando que genere listado de cortes/diámetros desde presets sin GUI.

## 6) QA / Validación
- [x] Identidades físicas y bandas de sanidad — Evidencia: `tests/test_identities.py`, `tests/test_sanity_bands.py`. Run: `python -m pytest -q tests/test_identities.py tests/test_sanity_bands.py`.
- [x] Tendencias verificables (boost, restricciones, fricción) — Evidencia: `tests/test_trends.py`. Run: `python -m pytest -q tests/test_trends.py`.
- [x] Contratos básicos 0D/1D — Evidencia: `tests/test_contract_0d.py`, `tests/test_contract_1d_bc.py` (integration). Run: `python -m pytest -q tests/test_contract_0d.py` (y opt-in `python -m pytest -m integration -q tests/test_contract_1d_bc.py`).
- [x] Presets legacy movidos a `presets/legacy/` — Evidencia: `AUDIT_REPORT.md`.
- [ ] Cobertura de regresión para presets legacy — Criterio: tests marcados `legacy` que carguen presets legacy y validen no-NaN/no-negatividad.

## 7) CLI Headless
- [x] CLI dyno/scope reproducible — Evidencia: `pywavedyn/cli.py`, `tests/test_cli_outputs.py`. Run: `python -m pytest -q tests/test_cli_outputs.py`.
