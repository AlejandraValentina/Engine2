from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.system
def test_dyno_import_compare_staged_schema(tmp_path: Path) -> None:
    source_csv = tmp_path / "real_dyno.csv"
    source_csv.write_text(
        "speed_rpm,power_kw,torque_lbft,map_abs_kpa,lambda_ch1,egt_f\n"
        "2000,20.20,71.11,95,0.92,1350\n"
        "3000,30.80,72.30,96,0.92,1380\n"
        "4000,42.30,74.51,97,0.91,1410\n",
        encoding="utf-8",
    )

    dataset_dir = tmp_path / "dyno_dataset"
    compare_path = tmp_path / "compare.json"
    staged_path = tmp_path / "staged.json"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "dyno-import",
            "--input",
            str(source_csv),
            "--out",
            str(dataset_dir),
            "--dataset-id",
            "k20_dyno_import",
            "--engine-id",
            "k20_dyno_import",
            "--preset-path",
            "presets/honda_k20.json",
            "--format",
            "csv",
            "--mapping",
            "rpm=speed_rpm,power_hp=power_kw,torque_nm=torque_lbft,map_kpa=map_abs_kpa,lambda=lambda_ch1,egt_c=egt_f",
            "--units",
            "power_hp=kw,torque_nm=lbft,map_kpa=kpa_abs,lambda=lambda,egt_c=f",
            "--notes",
            "system test dyno import",
            "--torque-mape-max",
            "0.5",
            "--power-mape-max",
            "0.5",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "dyno-compare",
            "--engine",
            str(Path("presets/honda_k20.json").resolve()),
            "--dataset",
            str(dataset_dir),
            "--out",
            str(compare_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "calibrate-staged",
            "--engine",
            str(Path("presets/honda_k20.json").resolve()),
            "--dataset",
            str(dataset_dir),
            "--out",
            str(staged_path),
            "--max-evals-per-stage",
            "5",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    imported_targets = _load(dataset_dir / "target_curve.json")
    compare_payload = _load(compare_path)
    staged_payload = _load(staged_path)

    jsonschema.validate(imported_targets, _load(Path("schemas/bench_targets.schema.json")))
    jsonschema.validate(compare_payload, _load(Path("schemas/bench_report.schema.json")))
    jsonschema.validate(staged_payload, _load(Path("schemas/staged_calibration.schema.json")))

    assert compare_payload["report_type"] == "compare_report"
    assert compare_payload["report_family"] == "analysis"
    assert compare_payload["context"]["dataset_id"] == "k20_dyno_import"
    assert compare_payload["context"]["engine_path"] == str(Path("presets/honda_k20.json").resolve())
    assert staged_payload["report_type"] == "staged_calibration_report"
    assert staged_payload["report_family"] == "analysis"
    assert staged_payload["context"]["dataset_id"] == "k20_dyno_import"
    assert staged_payload["context"]["base_engine_path"] == str(Path("presets/honda_k20.json").resolve())
    assert compare_payload["dataset"]["signals_present"]
    assert "signal_coverage" in compare_payload
    assert compare_payload["signal_evidence"]["groups"]["turbo"]["status"] == "present_not_compared"
    assert compare_payload["signal_evidence"]["groups"]["fueling"]["status"] == "compared"
    assert compare_payload["signal_evidence"]["groups"]["thermal"]["status"] == "present_not_compared"
    assert staged_payload["signal_evidence"]["groups"]["turbo"]["status"] == "present_not_compared"
    assert "diagnostics" in compare_payload
    assert "diagnostics" in staged_payload
    assert len(staged_payload["stages"]) == 6
    assert Path(staged_payload["artifacts"]["calibrated_engine"]).exists()
    assert Path(staged_payload["artifacts"]["benchmark_before"]).exists()
    assert Path(staged_payload["artifacts"]["benchmark_after"]).exists()
