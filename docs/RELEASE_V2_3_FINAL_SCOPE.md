# Release v2.3 FINAL scope

Scope frozen for v2.3 FINAL. No features outside this list.

## Deliverables (exact)
1) Validación externa con dataset mínimo (benchmarks reales) + contrato de error.
2) Turbo completo opt-in (mapas compresor/turbina + wastegate + intercooler) + tests de tendencia/sanidad.
3) Ingeniería de producto: performance budgets + fast path opt-in + stress tests numéricos.
4) Validación end-to-end de la aplicación (system tests) contra expectations y schemas.

## Definition of Done (por item)
Each item must include:
- CLI headless command (documented and reproducible).
- Stable JSON output with schema and schema test.
- Deterministic tests marked appropriately (unit/integration/system/perf/stress).
- Runtime bounded by max_steps/max_iters/time_budget where applicable.
- Documented in `internal/FEATURES.md` with evidence and command.

Rule: No features outside this scope.
