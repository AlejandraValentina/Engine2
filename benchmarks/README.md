# Benchmarks datasets

PyWaveDyn currently carries two benchmark dataset families:

- `regression_golden`: generated from simulator outputs for regression stability.
- `real_data`: imported from measured dyno data and stored as canonical benchmark packages when committed to the repo.

## Canonical package

A migrated benchmark package uses this structure:

```text
benchmarks/datasets/<dataset_id>/
  metadata.json
  target_curve.json
  source.csv        # present when the measured source file is committed
```

Minimum expectations:

- `metadata.json` includes traceability such as `dataset_id`, `engine_id`, `source_type`, `source_file`, `source_sha256`, and `error_contract`.
- `metadata.json` should also keep `signals_present` and `signal_evidence` aligned with the committed canonical signals so richer real-data packages stay explicit about what can and cannot be validated.
- `target_curve.json` contains canonical `points[]` in normalized units.
- `source.csv` is optional at the format level, but required when `metadata.source_file` points to a committed measured source.
- Canonical committed `real_data` packages must keep `source_sha256` aligned with the committed `source.csv`.
- Canonical committed `real_data` packages must not depend on legacy `targets.csv`.

The benchmark report is generated via:

```bash
python -m pywavedyn.cli benchmark --engine <engine.json> --dataset benchmarks/datasets/<dataset_id> --out bench_report.json
```

## Real-data transition policy

- `k20_like_real` and `v8_like_real` are migrated canonical real-data packages.
- `f1_like_real` remains an explicit placeholder legacy dataset until a real canonical package exists.
- Legacy `targets.csv` is only acceptable for placeholders that are clearly marked as such. It is not part of the canonical package format for migrated real datasets.
- In the current repo state, `benchmarks/datasets/k20_like_real/` and `benchmarks/datasets/v8_like_real/` are the only canonical committed `real_data` packages.
- In the current repo state, `benchmarks/datasets/f1_like_real/` is not a canonical committed real-data package; it stays as a documented placeholder legacy dataset with header-only `targets.csv`.
- In the current repo state, `k20_like_real` and `v8_like_real` remain torque/power-only committed evidence cases. They do not yet provide committed turbo, fueling, or thermal channels.
- `signal_evidence` keeps that state explicit using the official groups `contract_baseline`, `turbo`, `fueling`, and `thermal`.

See `docs/BENCHMARKS_METHOD.md` for the full error contract and dataset conventions.
