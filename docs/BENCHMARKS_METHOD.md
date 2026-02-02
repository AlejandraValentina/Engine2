# BENCHMARKS_METHOD

## Purpose
Benchmarks provide a reproducible error contract between the simulator and a dataset. There are two dataset types:

- **regression_golden**: generated from the current simulator outputs to detect regressions.
- **real_data**: external datasets imported via `bench-import` (not stored in this repo).

## Dataset Structure
Each dataset directory includes:

- `metadata.json`
  - `engine_id`, `source`, `notes`, and `error_contract` thresholds.
- `target_curve.json` (for regression_golden)
  - `points[]` with `rpm` and target values (`torque_nm`, `power_hp`).

For real data, use `bench-import` to generate `target_curve.json` from a CSV. Real datasets are not committed to the repo.

## Target Format
Example `target_curve.json`:
```json
{
  "engine_id": "k20_like_regression_golden",
  "points": [
    {"rpm": 3000, "torque_nm": 210.0, "power_hp": 88.4},
    {"rpm": 6000, "torque_nm": 205.0, "power_hp": 173.2}
  ]
}
```

## Metrics
Current benchmark evaluation computes:
- Torque MAPE and MAE
- Power MAPE and MAE
- `total_mape` = mean of torque and power MAPEs

The benchmark compares simulator outputs at the exact RPM points in the dataset (no interpolation).

## Error Contract
Each dataset defines thresholds in `metadata.json`:
```json
"error_contract": {
  "torque_mape_max": 0.02,
  "power_mape_max": 0.02
}
```

Guidance:
- `regression_golden`: tight tolerances (1-5% MAPE) since targets come from the current simulator.
- `real_data`: start broad (10-25% MAPE) and tighten as model calibration improves.

## Running Benchmarks
```bash
python -m pywavedyn.cli benchmark --engine presets/honda_k20.json --dataset benchmarks/datasets/honda_k20_na --out bench_report.json
```

## Importing Real Data
```bash
python -m pywavedyn.cli bench-import --csv curve.csv --out benchmarks/datasets/<name>/target_curve.json --engine-id <id> --torque-units lbft --power-units hp
```
