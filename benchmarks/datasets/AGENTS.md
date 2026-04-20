# AGENTS.md

## Role Of `benchmarks/datasets/`
- This folder contains benchmark assets, regression fixtures, canonical real-data packages, and a few documented transition cases.

## Non-Negotiable Dataset Rules
- Do not delete, normalize, or “clean up” datasets by intuition.
- Verify references in tests, docs, CLI, GUI, and schemas before changing any dataset or fixture.
- Do not touch golden regression fixtures or legacy compatibility assets without proving they are unused.

## Dataset Policy
- Canonical real-data packages should have `metadata.json` and `target_curve.json`, plus `source.csv` when the measured source is intentionally committed.
- Legacy `targets.csv` is only acceptable for explicit placeholders or documented migration cases.
- In the current repo state:
- `k20_like_real` and `v8_like_real` are canonical real-data packages.
- `f1_like_real` is a placeholder legacy case and must stay clearly marked as such until it is truly migrated.

## Migration Guidance
- If you migrate a placeholder to canonical form, update the related tests and docs in the same change.
- If you are unsure whether a dataset is transitional, keep it and document the uncertainty instead of deleting it.
