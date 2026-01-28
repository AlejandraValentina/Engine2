# Benchmarks datasets

Each dataset directory contains:
- `metadata.json` with engine_id, source, notes, and error_contract thresholds.
- `target_curve.json` with `points[]` (rpm + torque_nm/power_hp) and optional metadata.

Example structure:
```
benchmarks/datasets/<engine_id>/
  metadata.json
  target_curve.json
```

The benchmark report is generated via:
```
python -m pywavedyn.cli benchmark --engine <engine.json> --dataset benchmarks/datasets/<engine_id> --out bench_report.json
```
