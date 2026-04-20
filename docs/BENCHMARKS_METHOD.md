# BENCHMARKS_METHOD

## Purpose
Benchmarks provide a reproducible error contract between the simulator and a dataset. There are two dataset types:

- **regression_golden**: generated from the current simulator outputs to detect regressions.
- **real_data**: measured dyno datasets imported into the canonical benchmark-package format. They may live outside the repo or be committed when the source and traceability are available.

## Dataset Structure
Each dataset directory includes:

- `metadata.json`
  - traceability and import metadata.
- `target_curve.json`
  - `points[]` with `rpm` and target values.

For real data, use `dyno-import` or `bench-import` to generate the package. Canonical real-data packages may be committed to the repo when they include the measured source file and import metadata.

Canonical real-data packages should include:

- `metadata.json`
- `target_curve.json`
- `source.csv` when `metadata.source_file` references a committed measured CSV
- `source_sha256` in `metadata.json` that matches the committed `source.csv`
- `signals_present` and `signal_evidence` in `metadata.json` so optional-channel evidence stays explicit
- no legacy `targets.csv` dependency once the package is committed in canonical form

Legacy placeholder datasets may still exist during migration. Those placeholders must be explicitly marked in `metadata.json` and may carry a header-only `targets.csv` as a reminder that no canonical package has been committed yet.

## Target Format
Example `target_curve.json`:
```json
{
  "engine_id": "k20_like_regression_golden",
  "points": [
    {"rpm": 3000, "torque_nm": 210.0, "power_hp": 88.4},
    {"rpm": 6000, "torque_nm": 205.0, "power_hp": 173.2, "map_kpa": 96.0, "lambda": 0.92}
  ]
}
```

Canonical signals:

| Signal | Required | Canonical unit | Notes |
|---|---|---|---|
| `rpm` | yes | `rpm` | mandatory |
| `torque_nm` | one of torque/power | `N*m` | preserves measured torque if present |
| `power_hp` | one of torque/power | `hp` | preserves measured power if present |
| `boost_kpa` | no | `kPa_gauge` | gauge boost only |
| `map_kpa` | no | `kPa_abs` | absolute manifold pressure |
| `lambda` | no | `lambda` | unitless |
| `afr` | no | `afr_mass` | mass AFR |
| `egt_c` | no | `degC` | imported and traced even if not yet scored |

Supported import units:

| Signal | Supported source units |
|---|---|
| torque | `lbft`, `nm` |
| power | `hp`, `kw` |
| boost | `kpa_g`, `psi_g`, `bar_g` |
| MAP | `kpa_abs`, `psi_abs`, `bar_abs` |
| lambda | `lambda` |
| AFR | `afr` |
| EGT | `c`, `f`, `k` |

Mapping rules:
- `rpm` is mandatory.
- At least one of `torque_nm` or `power_hp` must be mapped.
- If both `afr` and `lambda` are present, both are preserved; importer emits a warning when they are inconsistent relative to `afr_stoich`.
- `boost_kpa` is always interpreted as gauge pressure and `map_kpa` as absolute pressure. The importer does not silently convert one into the other.

## Metrics
Current benchmark evaluation computes:
- Torque MAPE and MAE
- Power MAPE and MAE
- `total_mape` = mean of torque and power MAPEs
- Optional signal metrics are added when the dataset contains supported signals and the simulator exposes comparable predictions.

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
python -m pywavedyn.cli dyno-import --input curve.csv --out benchmarks/datasets/<name> --dataset-id <id> --engine-id <id> --preset-path presets/honda_k20.json --format csv --mapping rpm=speed,torque_nm=tq,power_hp=hp,map_kpa=map --units torque_nm=lbft,power_hp=hp,map_kpa=kpa_abs
```

## Repo transition status

- `benchmarks/datasets/k20_like_real/`: migrated canonical real-data package
- `benchmarks/datasets/v8_like_real/`: migrated canonical real-data package
- `benchmarks/datasets/f1_like_real/`: placeholder legacy dataset, not yet migrated to the canonical package format

Current committed real-data status:
- `k20_like_real` and `v8_like_real` are the only canonical committed `real_data` packages in this repo state.
- `f1_like_real` is not a canonical committed real-data package. It remains a documented placeholder legacy dataset until a real canonical package exists.
- In this repo state, the committed canonical real-data packages are still torque/power-only. A "richer canonical dataset" in this stage means a future committed package that truthfully adds optional channels such as `boost_kpa`, `map_kpa`, `lambda`, `afr`, or `egt_c` with the same traceability standard.

## Extended Comparison
`benchmark` and `dyno-compare` keep torque and power as the error-contract baseline. Optional signals are additive and do not change pass/fail unless the contract is explicitly extended in the future.

`signal_evidence` is now the small additive summary that keeps this honest:
- `contract_baseline` tracks torque/power evidence
- `turbo` tracks `boost_kpa`/`map_kpa`
- `fueling` tracks `lambda`/`afr`
- `thermal` tracks `egt_c`

Statuses distinguish between channels that are merely present in the dataset, channels that were actually compared in a report, and channels for which no committed evidence exists yet.

## Staged Calibration
`calibrate-staged` runs the following sequence:

| Stage | Param | Runs when | Current behavior |
|---|---|---|---|
| airflow / VE | `ve_scale` | torque or power present | active |
| friction | `friction_scale` | torque or power present | active |
| combustion | `burn_scale` | torque or power present | active as thermal-efficiency proxy |
| turbo | none yet | requires real boost/MAP plus supported turbo params | omitted and reported |
| thermal | none yet | requires EGT plus supported thermal params | omitted and reported |

If a stage lacks signals or lacks a physically-supported parameterization, it is skipped and the reason is written into the staged report.
