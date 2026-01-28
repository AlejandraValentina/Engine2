# VALIDATION_GUIDE

A) Default repo suite (must be green)
- `python -m pytest -q`

B) Warnings strict
- `python -m pytest -q -W error::RuntimeWarning`

C) Fast dev loop
- `python -m pytest -q -m "not slow"`

D) Pro dyno focus
- `python -m pytest -q -W error::RuntimeWarning -k pro_dyno`

E) Verificacion v2.2
- `python -m pytest -q -W error::RuntimeWarning`
- `python -m pytest -q`
- `python -m pytest -q -m integration`
- `python -m pytest -q -m legacy`
- `python -m pytest -q -m perf`

F) Verificacion v2.3 FINAL
- `python -m pytest -q -W error::RuntimeWarning`
- `python -m pytest -q`
- `python -m pytest -q -m integration`
- `python -m pytest -q -m legacy`
- `python -m pytest -q -m system`

G) Benchmarks
- `python -m pywavedyn.cli benchmark --engine presets/honda_k20.json --dataset benchmarks/datasets/honda_k20_na --out bench_report.json`

H) Scavenging metrics (intake_coupling)
- `overlap_flow_kg`: estimacion de masa intercambiada durante overlap, derivada de fraccion de overlap y caudal.
- `residual_fraction_est`: fraccion residual estimada = overlap_flow_kg / masa fresca por ciclo.
- `scavenging_index`: 1 - residual_fraction_est (mayor es mejor).

Notes
- 2026-01-27: Updated integration baseline bands (BMEP/VE/HP) to reflect current 0D calibration with valve-area penalty and revised friction scaling. Adjusted expectations document the new steady-state outputs without changing default feature flags.
