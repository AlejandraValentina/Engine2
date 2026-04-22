# Release v2.1 scope (frozen)

Este documento define el unico scope congelado para la release v2.1.

## Entregables exactos v2.1
1) Red 1D de admision headless (plenum -> runner -> valvula) + CLI + test + schema
2) Acople 0D<->1D en admision (opt-in) + metricas scavenging/overlap + tests
3) Runner de mapa parte-carga headless (rpm x throttle/load) + test + schema
4) Modelo termico opt-in (pared lumped) + gas thermally-perfect opt-in (cp(T), gamma(T)) + tests
5) Auto-calibracion opt-in contra curva objetivo + test + schema

## Regla de scope
No se aceptan features nuevas fuera de esta lista; solo bugfix/coverage.

## Definition of Done (por item)
- CLI/command reproducible.
- Test verde (unit o integration) con runtime acotado.
- Schema JSON validado (jsonschema).
- Evidencia actualizada en `internal/FEATURES.md`.
- Defaults intactos: opt-in => no-op cuando disabled.
