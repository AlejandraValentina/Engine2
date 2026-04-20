from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator
from pywavedyn.analysis_contract import REPORT_TYPE_VALIDATION_COMPARE
from pywavedyn.validation_compare import run_validation_batch


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
                "notes": "synthetic validation dataset",
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
def test_validation_compare_reports_adaptive_and_staged_results(tmp_path: Path) -> None:
    base = Engine()
    base.head.port_flow_efficiency = 0.78
    base.combustion.thermal_efficiency = 0.52
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
        points.append(
            {
                "rpm": rpm,
                "power_hp": float(cycle["mean_power_hp"]),
                "torque_nm": float(cycle["mean_torque_nm"]),
            }
        )

    dataset_dir = tmp_path / "adaptive_case"
    _write_dataset(dataset_dir, dataset_id="adaptive_case", points=points)

    payload = run_validation_batch(
        base,
        base.to_dict(),
        base_engine_path=Path("synthetic.json"),
        dataset_dirs=[dataset_dir],
        include_adaptive_toggle=True,
        include_turbo_toggle=False,
        include_staged_calibration=True,
        max_evals_per_stage=10,
    )

    assert payload["report_type"] == REPORT_TYPE_VALIDATION_COMPARE
    assert payload["report_family"] == "analysis"
    assert payload["context"]["dataset_id"] == "adaptive_case"
    assert payload["context"]["base_engine_path"] == "synthetic.json"

    case = payload["cases"][0]
    assert case["signal_evidence"]["groups"]["turbo"]["status"] == "not_available"
    adaptive_on = case["features"]["adaptive_on"]
    assert adaptive_on["evaluated"] is True
    assert adaptive_on["outcome"] in {"improved", "partial_improvement"}
    assert "torque_nm" in adaptive_on["delta_vs_baseline"]["signals_compared"]
    assert adaptive_on["signal_evidence"]["groups"]["contract_baseline"]["status"] == "compared"

    staged_after = case["features"]["staged_after"]
    assert staged_after["evaluated"] is True
    assert "staged_calibration" in staged_after
    assert staged_after["outcome"] in {"improved", "partial_improvement", "no_clear_benefit"}


@pytest.mark.integration
def test_validation_compare_reports_turbo_incremental_when_supported(tmp_path: Path) -> None:
    base = Engine()
    base.turbo = base.turbo.from_dict(
        {
            "enabled": True,
            "target_boost_kpa": 60.0,
            "compressor_map": [
                {"flow_kg_s": 0.03, "pr": 1.4},
                {"flow_kg_s": 0.08, "pr": 1.9}
            ],
            "turbine_map": [
                {"flow_kg_s": 0.03, "pr": 1.3},
                {"flow_kg_s": 0.08, "pr": 1.7}
            ],
            "response_model": {
                "enabled": False,
                "spool_rpm": 4200.0,
                "spool_width_rpm": 700.0,
                "flow_ref_kg_s": 0.18,
                "flow_width_kg_s": 0.05,
                "min_response": 0.2
            }
        }
    )

    target_engine = Engine.from_dict(base.to_dict())
    target_engine.turbo = target_engine.turbo.from_dict(
        {
            **target_engine.turbo.to_dict(),
            "response_model": {
                **dict(target_engine.turbo.response_model),
                "enabled": True,
                "spool_rpm": 3600.0
            }
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

    dataset_dir = tmp_path / "turbo_case"
    _write_dataset(dataset_dir, dataset_id="turbo_case", points=points)

    payload = run_validation_batch(
        base,
        base.to_dict(),
        base_engine_path=Path("synthetic_turbo.json"),
        dataset_dirs=[dataset_dir],
        include_adaptive_toggle=False,
        include_turbo_toggle=True,
        include_staged_calibration=False,
        max_evals_per_stage=5,
    )

    assert payload["report_type"] == REPORT_TYPE_VALIDATION_COMPARE
    assert payload["context"]["dataset_id"] == "turbo_case"

    case = payload["cases"][0]
    turbo_on = case["features"]["turbo_incremental_on"]
    assert turbo_on["evaluated"] is True
    assert "boost_kpa" in turbo_on["delta_vs_baseline"]["signals_compared"]
    assert turbo_on["outcome"] in {"improved", "partial_improvement", "tradeoff", "no_clear_benefit"}
    assert turbo_on["signal_evidence"]["groups"]["turbo"]["status"] == "compared"
