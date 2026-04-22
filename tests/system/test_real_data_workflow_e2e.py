from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.system
@pytest.mark.parametrize(
    ("dataset_id", "engine_id", "preset_path", "source_csv", "torque_limit", "power_limit"),
    [
        (
            "k20_like_real",
            "k20_like_real",
            "presets/honda_k20.json",
            "benchmarks/datasets/k20_like_real/source.csv",
            "0.12",
            "0.12",
        ),
        (
            "v8_like_real",
            "v8_like_real",
            "presets/chevy_350.json",
            "benchmarks/datasets/v8_like_real/source.csv",
            "0.15",
            "0.15",
        ),
    ],
)
def test_real_data_workflow_e2e(
    tmp_path: Path,
    dataset_id: str,
    engine_id: str,
    preset_path: str,
    source_csv: str,
    torque_limit: str,
    power_limit: str,
) -> None:
    dataset_dir = tmp_path / dataset_id
    bench_before = tmp_path / f"{dataset_id}_bench_before.json"
    calib_dir = tmp_path / f"{dataset_id}_calibration"
    calib_report = calib_dir / "calib_report.json"
    calibrated_engine = calib_dir / "calibrated_engine.json"
    bench_after = calib_dir / "bench_after.json"

    _run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "bench-import",
            "--csv",
            str(Path(source_csv).resolve()),
            "--out",
            str(dataset_dir),
            "--dataset-id",
            dataset_id,
            "--engine-id",
            engine_id,
            "--preset-path",
            preset_path,
            "--torque-units",
            "lbft",
            "--power-units",
            "hp",
            "--notes",
            f"{dataset_id} imported in E2E test",
            "--torque-mape-max",
            torque_limit,
            "--power-mape-max",
            power_limit,
        ]
    )

    assert (dataset_dir / "source.csv").exists()
    assert (dataset_dir / "metadata.json").exists()
    assert (dataset_dir / "target_curve.json").exists()

    imported_meta = _load_json(dataset_dir / "metadata.json")
    imported_targets = _load_json(dataset_dir / "target_curve.json")
    jsonschema.validate(
        instance=imported_targets,
        schema=_load_json(Path("schemas/bench_targets.schema.json")),
    )
    assert imported_meta["dataset_id"] == dataset_id
    assert imported_meta["engine_id"] == engine_id
    assert imported_meta["preset_path"] == preset_path
    assert imported_meta["source_type"] == "real_data"
    assert imported_meta["source_file"] == "source.csv"
    assert imported_meta["source_sha256"] == _sha256(dataset_dir / "source.csv")
    assert imported_meta["signals_present"] == ["power_hp", "torque_nm"]
    assert imported_meta["signal_evidence"]["groups"]["contract_baseline"]["status"] == "available"
    assert imported_meta["signal_evidence"]["groups"]["turbo"]["status"] == "not_available"
    assert "error_contract" in imported_meta
    assert not (dataset_dir / "targets.csv").exists()

    _run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "benchmark",
            "--engine",
            str(Path(preset_path).resolve()),
            "--dataset",
            str(dataset_dir),
            "--out",
            str(bench_before),
        ]
    )

    bench_before_payload = _load_json(bench_before)
    jsonschema.validate(
        instance=bench_before_payload,
        schema=_load_json(Path("schemas/bench_report.schema.json")),
    )
    assert bench_before_payload["dataset"]["dataset_id"] == dataset_id
    assert bench_before_payload["dataset"]["engine_id"] == engine_id
    assert bench_before_payload["dataset"]["preset_path"] == preset_path
    assert bench_before_payload["dataset"]["source_file"] == "source.csv"
    assert bench_before_payload["signal_evidence"]["groups"]["contract_baseline"]["status"] == "compared"
    assert bench_before_payload["signal_evidence"]["groups"]["turbo"]["status"] == "not_available"
    assert "pass" in bench_before_payload["contract"]

    _run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "calibrate",
            "--engine",
            str(Path(preset_path).resolve()),
            "--target",
            str(dataset_dir / "target_curve.json"),
            "--out",
            str(calib_report),
            "--max-evals",
            "10",
            "--params",
            "ve_scale,friction_scale,burn_scale",
        ]
    )

    assert calibrated_engine.exists()
    calib_payload = _load_json(calib_report)
    jsonschema.validate(
        instance=calib_payload,
        schema=_load_json(Path("schemas/calib_report.schema.json")),
    )
    assert calib_payload["preset_base_path"].endswith(preset_path.replace("/", "\\"))
    assert calib_payload["dataset"]["dataset_id"] == dataset_id
    assert calib_payload["dataset"]["engine_id"] == engine_id
    assert set(calib_payload["params_final"].keys()) <= {"ve_scale", "friction_scale", "burn_scale"}
    assert set(calib_payload["parameter_values"].keys()) <= {"ve_scale", "friction_scale", "burn_scale"}
    assert calib_payload["artifacts"]["calibrated_engine"].endswith("calibrated_engine.json")

    _run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "benchmark",
            "--engine",
            str(calibrated_engine),
            "--dataset",
            str(dataset_dir),
            "--out",
            str(bench_after),
        ]
    )

    bench_after_payload = _load_json(bench_after)
    jsonschema.validate(
        instance=bench_after_payload,
        schema=_load_json(Path("schemas/bench_report.schema.json")),
    )
    assert bench_after_payload["dataset"]["dataset_id"] == dataset_id
    assert bench_after_payload["dataset"]["engine_id"] == engine_id
    assert bench_after_payload["signal_evidence"]["groups"]["contract_baseline"]["status"] == "compared"
    assert "total_mape" in bench_after_payload["errors"]
    assert "pass" in bench_after_payload["contract"]
