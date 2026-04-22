# Release v2.0 checks (executables)

Este checklist cierra el scope congelado de v2.0 con comandos reproducibles.

## 1) Acople 0D↔1D bidireccional (Wave Scope v1)
- **Comando:** `python -m pytest -m integration -q tests/integration/test_0d_1d_bidirectional_backpressure_affects_cycle.py`
- **Archivos clave:** `core/simulator.py`, `core/thermo.py`, `tests/integration/test_0d_1d_bidirectional_backpressure_affects_cycle.py`

## 2) Síntesis multi-cilindro verificada (audio)
- **Comando:** `python -m pytest -q tests/test_audio_multicyl_wav_nonempty.py`
- **Archivos clave:** `acoustics/audio_generator.py`, `tests/test_audio_multicyl_wav_nonempty.py`

## 3) Barridos automáticos sin GUI (sweep headless)
- **Comando:** `python -m pytest -q tests/test_headless_sweep_runner_length.py`
- **Archivos clave:** `pywavedyn/cli.py`, `tests/test_headless_sweep_runner_length.py`

## 4) Reporte/cut-list reproducible por CLI
- **Comando:** `python -m pytest -q tests/test_cutlist_cli_generates_expected_keys.py`
- **Archivos clave:** `pywavedyn/cli.py`, `schemas/cutlist.schema.json`, `tests/test_cutlist_cli_generates_expected_keys.py`

## 5) Cobertura de regresión para presets legacy
- **Comando:** `python -m pytest -q -m legacy`
- **Archivos clave:** `tests/legacy/test_legacy_presets_load_and_run_0d.py`, `presets/legacy/`
