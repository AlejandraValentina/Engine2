from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator
from pywavedyn.analysis_contract import REPORT_TYPE_STAGED_CALIBRATION
from pywavedyn.staged_calibration import run_staged_calibration


def _dataset_package(dataset_dir: Path, *, engine_id: str, preset_path: str, points: list[dict]) -> None:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "metadata.json").write_text(
        json.dumps(
            {
                "dataset_id": engine_id,
                "engine_id": engine_id,
                "preset_path": preset_path,
                "source_type": "real_data",
                "source_file": "synthetic.json",
                "source_sha256": "synthetic",
                "torque_units": "nm",
                "power_units": "hp",
                "notes": "synthetic adaptive combustion dataset",
                "error_contract": {"torque_mape_max": 1.0, "power_mape_max": 1.0},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (dataset_dir / "target_curve.json").write_text(
        json.dumps({"engine_id": engine_id, "points": points}, indent=2),
        encoding="utf-8",
    )


@pytest.mark.integration
def test_staged_calibration_can_tune_adaptive_combustion_globals(tmp_path: Path) -> None:
    base = Engine()
    base.head.port_flow_efficiency = 0.78
    base.combustion.thermal_efficiency = 0.52
    base.combustion.afr = 14.7
    base.combustion.adaptive_model = {
        "enabled": True,
        "duration_scale": 1.0,
        "ca50_offset_deg": 0.0,
        "duration_rpm_per_krpm": 1.5,
        "duration_load_per_bar": -0.5,
        "ca50_load_per_bar": -0.15,
    }

    target_engine = Engine.from_dict(base.to_dict())
    target_engine.combustion.adaptive_model = {
        **dict(target_engine.combustion.adaptive_model),
        "duration_scale": 0.9,
        "ca50_offset_deg": -2.0,
    }

    sim = CylinderSimulator(target_engine)
    points = []
    for rpm in (2500.0, 4000.0, 5500.0):
        cycle = sim.run_cycle(rpm)
        points.append(
            {
                "rpm": rpm,
                "power_hp": float(cycle["mean_power_hp"]),
                "torque_nm": float(cycle["mean_torque_nm"]),
            }
        )

    dataset_dir = tmp_path / "adaptive_dataset"
    _dataset_package(dataset_dir, engine_id="adaptive_case", preset_path="synthetic.json", points=points)

    report, calibrated_raw, bench_before, bench_after = run_staged_calibration(
        base,
        base.to_dict(),
        base_engine_path=Path("synthetic.json"),
        dataset_dir=dataset_dir,
        max_evals_per_stage=10,
    )

    assert report["report_type"] == REPORT_TYPE_STAGED_CALIBRATION
    assert report["context"]["dataset_id"] == "adaptive_case"
    assert report["context"]["base_engine_path"] == "synthetic.json"
    adaptive_stage = next(stage for stage in report["stages"] if stage["stage_name"] == "combustion_adaptive")
    assert adaptive_stage["signals_used"] == ["power_hp", "torque_nm"]
    assert report["combustion_before"]["adaptive_enabled"] is True
    assert report["combustion_after"]["adaptive_enabled"] is True
    assert "adaptive_duration_scale" in report["final_params"] or "adaptive_ca50_offset_deg" in report["final_params"]
    assert bench_after["errors"]["total_mape"] <= bench_before["errors"]["total_mape"]
    assert calibrated_raw["combustion"]["adaptive_model"]["enabled"] is True
