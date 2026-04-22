from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator
from pywavedyn.analysis_contract import REPORT_TYPE_STAGED_CALIBRATION
from pywavedyn.staged_calibration import run_staged_calibration


def _write_dataset(dataset_dir: Path, points: list[dict]) -> None:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "metadata.json").write_text(
        json.dumps(
            {
                "dataset_id": "turbo_stage_case",
                "engine_id": "turbo_stage_case",
                "preset_path": "synthetic_turbo.json",
                "source_type": "real_data",
                "source_file": "synthetic.json",
                "source_sha256": "synthetic",
                "torque_units": "nm",
                "power_units": "hp",
                "notes": "synthetic turbo stage dataset",
                "error_contract": {"torque_mape_max": 1.0, "power_mape_max": 1.0},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (dataset_dir / "target_curve.json").write_text(
        json.dumps({"engine_id": "turbo_stage_case", "points": points}, indent=2),
        encoding="utf-8",
    )


@pytest.mark.integration
def test_staged_calibration_can_use_turbo_stage_when_boost_signal_exists(tmp_path: Path) -> None:
    base = Engine()
    base.turbo = base.turbo.from_dict(
        {
            "enabled": True,
            "target_boost_kpa": 60.0,
            "compressor_map": [
                {"flow_kg_s": 0.03, "pr": 1.4},
                {"flow_kg_s": 0.08, "pr": 1.9},
            ],
            "turbine_map": [
                {"flow_kg_s": 0.03, "pr": 1.3},
                {"flow_kg_s": 0.08, "pr": 1.7},
            ],
            "response_model": {
                "enabled": True,
                "spool_rpm": 4200.0,
                "spool_width_rpm": 700.0,
                "flow_ref_kg_s": 0.18,
                "flow_width_kg_s": 0.05,
                "min_response": 0.2,
            },
        }
    )

    target_engine = Engine.from_dict(base.to_dict())
    target_engine.turbo = target_engine.turbo.from_dict(
        {
            **target_engine.turbo.to_dict(),
            "target_boost_kpa": 69.0,
            "response_model": {
                **dict(target_engine.turbo.response_model),
                "enabled": True,
                "spool_rpm": 3700.0,
            },
        }
    )

    sim = CylinderSimulator(target_engine)
    points = []
    for rpm in (2500.0, 4500.0, 6000.0):
        cycle = sim.run_cycle(rpm)
        points.append(
            {
                "rpm": rpm,
                "power_hp": float(cycle["mean_power_hp"]),
                "torque_nm": float(cycle["mean_torque_nm"]),
                "boost_kpa": float(cycle["boost_kpa"]),
            }
        )

    dataset_dir = tmp_path / "turbo_dataset"
    _write_dataset(dataset_dir, points)

    report, calibrated_raw, bench_before, bench_after = run_staged_calibration(
        base,
        base.to_dict(),
        base_engine_path=Path("synthetic_turbo.json"),
        dataset_dir=dataset_dir,
        max_evals_per_stage=10,
    )

    assert report["report_type"] == REPORT_TYPE_STAGED_CALIBRATION
    assert report["context"]["dataset_id"] == "turbo_stage_case"
    assert report["signal_evidence"]["groups"]["turbo"]["status"] == "compared"
    turbo_stage = next(stage for stage in report["stages"] if stage["stage_name"] == "turbo")
    assert "boost_kpa" in turbo_stage["signals_used"]
    assert turbo_stage["accepted"] is True
    assert "turbo_target_boost_scale" in report["final_params"] or "turbo_spool_rpm_offset" in report["final_params"]
    assert turbo_stage["after_metrics"]["objective_filtered"] <= turbo_stage["before_metrics"]["objective_filtered"]
    assert any(diag["id"] == "turbo_stage_helped" for diag in report.get("diagnostics", []))
