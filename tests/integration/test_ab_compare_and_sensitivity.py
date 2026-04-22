from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator
from pywavedyn.analysis_contract import REPORT_TYPE_AB_COMPARE, REPORT_TYPE_SENSITIVITY_LOCAL
from pywavedyn.ab_sensitivity import run_ab_compare, run_local_sensitivity
from pywavedyn.combustion_mode import apply_adaptive_combustion_mode


def _write_dataset(dataset_dir: Path, *, dataset_id: str, points: list[dict]) -> None:
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "metadata.json").write_text(
        json.dumps(
            {
                "dataset_id": dataset_id,
                "engine_id": dataset_id,
                "preset_path": "synthetic.json",
                "source_type": "real_data",
                "source_file": "synthetic.json",
                "source_sha256": "synthetic",
                "notes": "synthetic ab/sensitivity dataset",
                "error_contract": {"torque_mape_max": 1.0, "power_mape_max": 1.0},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (dataset_dir / "target_curve.json").write_text(
        json.dumps({"engine_id": dataset_id, "points": points}, indent=2),
        encoding="utf-8",
    )


@pytest.mark.integration
def test_ab_compare_reports_improvement_for_adaptive_case(tmp_path: Path) -> None:
    base = Engine()
    base.combustion.adaptive_model = {
        "enabled": False,
        "duration_scale": 1.0,
        "ca50_offset_deg": 0.0,
        "duration_rpm_per_krpm": 1.6,
        "duration_load_per_bar": -0.6,
        "ca50_load_per_bar": -0.18,
    }
    target_engine = Engine.from_dict(base.to_dict())
    target_engine.combustion.adaptive_model = {
        **dict(target_engine.combustion.adaptive_model),
        "enabled": True,
        "duration_scale": 0.9,
        "ca50_offset_deg": -2.0,
    }
    sim = CylinderSimulator(target_engine)
    points = []
    for rpm in (2500.0, 4000.0, 5500.0):
        cycle = sim.run_cycle(rpm)
        points.append({"rpm": rpm, "power_hp": float(cycle["mean_power_hp"]), "torque_nm": float(cycle["mean_torque_nm"])})
    dataset_dir = tmp_path / "adaptive_case"
    _write_dataset(dataset_dir, dataset_id="adaptive_case", points=points)

    engine_a, raw_a, _ = apply_adaptive_combustion_mode(base, base.to_dict(), mode="off")
    engine_b, raw_b, _ = apply_adaptive_combustion_mode(base, base.to_dict(), mode="on")
    report = run_ab_compare(engine_a, raw_a, engine_b, raw_b, dataset_dir=dataset_dir, label_a="adaptive_off", label_b="adaptive_on")

    assert report["report_type"] == REPORT_TYPE_AB_COMPARE
    assert report["context"]["dataset_id"] == "adaptive_case"
    assert report["comparison"]["outcome"] in {"improved", "partial_improvement"}
    assert "torque_nm" in report["comparison"]["delta_a_to_b"]["signals_compared"]


@pytest.mark.integration
def test_local_sensitivity_ranks_supported_params_and_marks_unsupported(tmp_path: Path) -> None:
    base = Engine()
    base.combustion.adaptive_model = {
        "enabled": True,
        "duration_scale": 1.0,
        "ca50_offset_deg": 0.0,
        "duration_rpm_per_krpm": 1.4,
        "duration_load_per_bar": -0.5,
        "ca50_load_per_bar": -0.15,
    }
    target_engine = Engine.from_dict(base.to_dict())
    target_engine.head.port_flow_efficiency *= 1.1
    sim = CylinderSimulator(target_engine)
    points = []
    for rpm in (2500.0, 4000.0, 5500.0):
        cycle = sim.run_cycle(rpm)
        points.append({"rpm": rpm, "power_hp": float(cycle["mean_power_hp"]), "torque_nm": float(cycle["mean_torque_nm"])})
    dataset_dir = tmp_path / "sensitivity_case"
    _write_dataset(dataset_dir, dataset_id="sensitivity_case", points=points)

    payload = run_local_sensitivity(
        base,
        base.to_dict(),
        dataset_dir=dataset_dir,
        params=["ve_scale", "friction_scale", "adaptive_duration_scale", "turbo_spool_rpm_offset"],
    )

    assert payload["report_type"] == REPORT_TYPE_SENSITIVITY_LOCAL
    assert payload["context"]["dataset_id"] == "sensitivity_case"
    results = {entry["param"]: entry for entry in payload["params"]}
    assert results["ve_scale"]["supported"] is True
    assert results["ve_scale"]["overall_influence_score"] is not None
    assert results["turbo_spool_rpm_offset"]["supported"] is False
    assert "requires a turbocharged engine" in results["turbo_spool_rpm_offset"]["note"].lower()
    assert "torque_nm" in payload["summary"]["rankings_by_signal"]
    assert payload["summary"]["robustness_by_signal"]["torque_nm"]["level"] in {
        "low_sensitivity",
        "moderate_sensitivity",
        "high_sensitivity",
    }
