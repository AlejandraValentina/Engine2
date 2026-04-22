# AGENTS.md

## Purpose
- PyWaveDyn is a simulation and validation repo for engine modeling, dyno comparison, staged calibration, diagnostics, and lightweight GUI workflows.
- Treat reusable backend logic as the source of truth. GUI, docs, and exported artifacts should reflect backend behavior, not redefine it.

## Scope And Inheritance
- These root rules apply repo-wide.
- If a subdirectory contains its own `AGENTS.md`, treat it as a local specialization that complements this root file rather than replacing it.

## Source Of Truth Docs
Read in this order when you need current project context:
1. `README.md`
2. `docs/RUNBOOK.md`
3. `docs/GUI_OVERVIEW.md`
4. `docs/BENCHMARKS_METHOD.md`
5. `docs/TECHNICAL_SPECS_V2.md`
6. `docs/internal/FEATURES.md`
7. `docs/internal/VALIDATION_GUIDE.md`

- Use `docs/internal/*` for evidence and history, not as a shortcut to invent behavior not backed by code/tests.

## Core Working Rules
- CLI and reusable backend modules come first. Prefer `pywavedyn/*` and `core/*` integration points over GUI-only or script-only logic.
- Do not duplicate compare, calibration, diagnostics, sensitivity, optimization, parsing, or normalization logic across core, CLI, and GUI.
- Keep defaults and legacy behavior stable. New behavior must be opt-in unless the repo already proves a safe migration path.
- Schema and report changes must be additive unless a user explicitly asks for a breaking migration.

## Datasets, Benchmarks, And Fixtures
- Do not delete, rename, or rewrite datasets, golden fixtures, `_real` packages, or validation cases by intuition.
- Verify references in tests, docs, CLI, GUI, and schemas before touching benchmark assets.
- Canonical real-data packages use `metadata.json` plus `target_curve.json`, with `source.csv` when the measured source is intentionally committed.
- Legacy `targets.csv` is only acceptable for explicit placeholders or documented transition cases.
- Current transition policy:
- `benchmarks/datasets/k20_like_real` and `benchmarks/datasets/v8_like_real` are canonical real-data packages.
- `benchmarks/datasets/f1_like_real` is a placeholder legacy case, not a validated real-data package.

## Cleanup Rules
- Before deleting or moving files, confirm there are no references from imports, tests, docs, scripts, CLI, GUI, or schemas.
- If a file looks stale but you cannot prove it is safe to remove, keep it and mark it as suspicious.
- Keep cleanup changes separate from functional changes when practical so review and rollback stay clear.
- Generated local outputs should live in ignored, traceable locations. Do not leave ad hoc artifacts loose in repo root.

## Testing Expectations
- Run targeted tests for the area you changed. Prefer the smallest useful slice first, then broader coverage when risk justifies it.
- Do not claim compatibility, migration safety, or bug fixes without test evidence when feasible.
- Preserve legacy/system/integration expectations; do not silently "fix" tests by weakening useful coverage.
- GUI tests/headless exports should use `QT_QPA_PLATFORM=offscreen`.

## Documentation Expectations
- When behavior, workflows, or dataset policy changes, update the relevant docs in the source-of-truth set.
- Do not present audit hypotheses as confirmed bugs without code/test/doc evidence.
- Mark stale, legacy, placeholder, or transitional material explicitly instead of mixing it with current guidance.

## Final Report Expectations
Final answers should include:
- summary of changes
- files modified
- tests or checks run
- limits/risks still open
- exact verification commands when useful

## Definition Of Done
- The change is implemented in the right layer.
- Tests/docs are aligned with the real behavior.
- Legacy compatibility and additive schema/report behavior are preserved unless explicitly requested otherwise.
- Any remaining uncertainty is called out plainly instead of hidden.
