# Release v2.2 scope (frozen)

Este documento define el unico scope congelado para la release v2.2.

## Entregables exactos v2.2
1) Full multi-cilindro 1D network (admision + escape simultaneo) + CLI + schema + tests
2) Benchmarks externos minimos: 2 presets nuevos + validation_cases + selfcheck expectations + schema test
3) Residuals -> combustion opt-in (usa scavenging/residual_fraction_est) + tests de tendencia
4) Optimize runner determinista (seed fija) + schema + tests
5) Performance contracts: budgets de steps + fast path opt-in + tests de paridad

## Regla de scope
No se aceptan features nuevas fuera de esta lista; solo bugfix/coverage.

## Definition of Done (por item)
- CLI/command reproducible.
- Test verde (unit o integration/perf) con runtime acotado.
- Schema JSON validado (jsonschema).
- Evidencia actualizada en `internal/FEATURES.md`.
- Defaults intactos: opt-in => no-op cuando disabled.
