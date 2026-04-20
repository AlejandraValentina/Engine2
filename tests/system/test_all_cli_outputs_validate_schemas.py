from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


def _load_schema(name: str) -> dict:
    path = Path("schemas") / name
    return json.loads(path.read_text(encoding="utf-8"))


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


@pytest.mark.system
def test_all_cli_outputs_validate_schemas(tmp_path: Path) -> None:
    engine = Path("presets/legacy/custom_twin_230cc.json").resolve()
    benchmark_engine = Path("presets/honda_k20.json").resolve()
    bench_dataset = Path("benchmarks/datasets/k20_like_real").resolve()

    dyno_path = tmp_path / "dyno.json"
    _run([sys.executable, "-m", "pywavedyn.cli", "dyno", "--engine", str(engine), "--rpm", "2000", "--out", str(dyno_path)])
    jsonschema.validate(instance=json.loads(dyno_path.read_text()), schema=_load_schema("dyno.schema.json"))

    scope_path = tmp_path / "scope.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "scope",
        "--engine",
        str(engine),
        "--rpm",
        "2000",
        "--cycles",
        "1",
        "--max-steps",
        "40",
        "--out",
        str(scope_path),
    ])
    jsonschema.validate(instance=json.loads(scope_path.read_text()), schema=_load_schema("scope.schema.json"))

    intake_path = tmp_path / "intake_scope.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "intake-scope",
        "--engine",
        str(engine),
        "--max-steps",
        "30",
        "--out",
        str(intake_path),
    ])
    jsonschema.validate(instance=json.loads(intake_path.read_text()), schema=_load_schema("intake_scope.schema.json"))

    sweep_path = tmp_path / "sweep.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "sweep",
        "--engine",
        str(engine),
        "--rpm",
        "2000",
        "--points",
        "2",
        "--span-mm",
        "50",
        "--out",
        str(sweep_path),
    ])
    jsonschema.validate(instance=json.loads(sweep_path.read_text()), schema=_load_schema("sweep.schema.json"))

    map_path = tmp_path / "map.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "map",
        "--engine",
        str(engine),
        "--rpm-grid",
        "2000",
        "--throttle-grid",
        "0.6",
        "--out",
        str(map_path),
    ])
    map_payload = json.loads(map_path.read_text())
    jsonschema.validate(instance=map_payload, schema=_load_schema("map.schema.json"))
    assert map_payload["observable_semantics"]["ve_actual"]["cross_mode_relation"] == "comparable_not_identical"

    target_path = tmp_path / "target.json"
    target_payload = {
        "points": [
            {"rpm": 2000, "torque_nm": 120.0},
            {"rpm": 3000, "torque_nm": 140.0},
        ]
    }
    target_path.write_text(json.dumps(target_payload), encoding="utf-8")

    calib_path = tmp_path / "calib.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "calibrate",
        "--engine",
        str(engine),
        "--target",
        str(target_path),
        "--out",
        str(calib_path),
        "--max-evals",
        "5",
    ])
    jsonschema.validate(instance=json.loads(calib_path.read_text()), schema=_load_schema("calib_report.schema.json"))

    opt_path = tmp_path / "opt.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "optimize",
        "--engine",
        str(engine),
        "--target",
        str(target_path),
        "--param",
        "intake.runner_length",
        "--bounds",
        "0.20,0.25",
        "--seed",
        "123",
        "--max-evals",
        "5",
        "--out",
        str(opt_path),
    ])
    jsonschema.validate(instance=json.loads(opt_path.read_text()), schema=_load_schema("opt_report.schema.json"))

    opt_guided_path = tmp_path / "opt_guided.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "optimize-guided",
        "--engine",
        str(engine),
        "--objective",
        "dataset_error",
        "--params",
        "burn_scale,friction_scale",
        "--target",
        str(target_path),
        "--max-signal-mape",
        "torque_nm=10.0",
        "--max-evals",
        "8",
        "--out",
        str(opt_guided_path),
    ])
    jsonschema.validate(instance=json.loads(opt_guided_path.read_text()), schema=_load_schema("optimize_guided.schema.json"))

    full_scope_path = tmp_path / "full_scope.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "full-scope",
        "--engine",
        str(engine),
        "--duration",
        "0.01",
        "--target-dx",
        "0.1",
        "--max-steps",
        "800",
        "--out",
        str(full_scope_path),
    ])
    full_scope_payload = json.loads(full_scope_path.read_text())
    jsonschema.validate(instance=full_scope_payload, schema=_load_schema("full_scope.schema.json"))
    assert full_scope_payload["observable_semantics"]["ve_actual"]["cross_mode_relation"] == "comparable_not_identical"

    bench_path = tmp_path / "bench.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "benchmark",
        "--engine",
        str(benchmark_engine),
        "--dataset",
        str(bench_dataset),
        "--out",
        str(bench_path),
    ])
    jsonschema.validate(instance=json.loads(bench_path.read_text()), schema=_load_schema("bench_report.schema.json"))

    expectations_path = tmp_path / "expectations.json"
    expectations_payload = {
        "cases": [
            {
                "file": str(Path("validation_cases/k20_like.json").resolve()),
                "rpm": [3000],
                "power_hp_min": [0.0],
                "power_hp_max": [500.0],
            }
        ]
    }
    expectations_path.write_text(json.dumps(expectations_payload), encoding="utf-8")

    selfcheck_path = tmp_path / "selfcheck.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "selfcheck",
        "--expectations",
        str(expectations_path),
        "--out",
        str(selfcheck_path),
    ])
    jsonschema.validate(instance=json.loads(selfcheck_path.read_text()), schema=_load_schema("selfcheck.schema.json"))

    cutlist_path = tmp_path / "cutlist.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "cutlist",
        "--engine",
        str(engine),
        "--out",
        str(cutlist_path),
    ])
    jsonschema.validate(instance=json.loads(cutlist_path.read_text()), schema=_load_schema("cutlist.schema.json"))

    csv_path = tmp_path / "curve.csv"
    csv_path.write_text("rpm,hp,tq\n2000,40,80\n3000,55,90\n", encoding="utf-8")
    dataset_dir = tmp_path / "toy_dataset"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "bench-import",
        "--csv",
        str(csv_path),
        "--out",
        str(dataset_dir),
        "--dataset-id",
        "toy_dataset",
        "--engine-id",
        "toy",
        "--preset-path",
        "presets/honda_k20.json",
        "--torque-units",
        "lbft",
        "--power-units",
        "hp",
        "--notes",
        "toy dataset",
    ])
    jsonschema.validate(
        instance=json.loads((dataset_dir / "target_curve.json").read_text(encoding="utf-8")),
        schema=_load_schema("bench_targets.schema.json"),
    )

    flexible_csv = tmp_path / "flex_dyno.csv"
    flexible_csv.write_text("speed,pwr,trq,map_abs\n2000,40,80,95\n3000,55,90,96\n", encoding="utf-8")
    flexible_dataset = tmp_path / "flex_dataset"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "dyno-import",
        "--input",
        str(flexible_csv),
        "--out",
        str(flexible_dataset),
        "--dataset-id",
        "flex_dataset",
        "--engine-id",
        "toy",
        "--preset-path",
        "presets/honda_k20.json",
        "--format",
        "csv",
        "--mapping",
        "rpm=speed,power_hp=pwr,torque_nm=trq,map_kpa=map_abs",
        "--units",
        "power_hp=hp,torque_nm=lbft,map_kpa=kpa_abs",
        "--notes",
        "flex dataset",
    ])
    jsonschema.validate(
        instance=json.loads((flexible_dataset / "target_curve.json").read_text(encoding="utf-8")),
        schema=_load_schema("bench_targets.schema.json"),
    )

    staged_path = tmp_path / "staged_calibration.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "calibrate-staged",
        "--engine",
        str(benchmark_engine),
        "--dataset",
        str(flexible_dataset),
        "--out",
        str(staged_path),
        "--max-evals-per-stage",
        "3",
    ])
    jsonschema.validate(instance=json.loads(staged_path.read_text()), schema=_load_schema("staged_calibration.schema.json"))

    validation_path = tmp_path / "validation_compare.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "validate-features",
        "--engine",
        str(benchmark_engine),
        "--datasets",
        str(flexible_dataset),
        "--out",
        str(validation_path),
        "--with-adaptive-toggle",
        "--with-staged-calibration",
        "--max-evals-per-stage",
        "3",
    ])
    jsonschema.validate(instance=json.loads(validation_path.read_text()), schema=_load_schema("validation_compare.schema.json"))

    ab_compare_path = tmp_path / "ab_compare.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "compare-ab",
        "--engine-a",
        str(benchmark_engine),
        "--engine-b",
        str(benchmark_engine),
        "--dataset",
        str(flexible_dataset),
        "--label-a",
        "baseline",
        "--label-b",
        "adaptive_on",
        "--adaptive-combustion-b",
        "on",
        "--out",
        str(ab_compare_path),
    ])
    jsonschema.validate(instance=json.loads(ab_compare_path.read_text()), schema=_load_schema("ab_compare.schema.json"))

    sensitivity_path = tmp_path / "sensitivity_local.json"
    _run([
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "sensitivity-local",
        "--engine",
        str(benchmark_engine),
        "--dataset",
        str(flexible_dataset),
        "--params",
        "ve_scale,friction_scale,burn_scale",
        "--out",
        str(sensitivity_path),
    ])
    jsonschema.validate(instance=json.loads(sensitivity_path.read_text()), schema=_load_schema("sensitivity_local.schema.json"))
