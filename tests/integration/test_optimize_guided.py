from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.optimize_runner import optimize_guided
from core.thermo import CylinderSimulator


def _write_target(path: Path, points: list[dict]) -> None:
    path.write_text(json.dumps({"points": points}, indent=2), encoding="utf-8")


@pytest.mark.integration
def test_optimize_guided_reduces_dataset_error_for_safe_params(tmp_path: Path) -> None:
    base = Engine()
    target_engine = Engine.from_dict(base.to_dict())
    target_engine.combustion.thermal_efficiency *= 1.1

    sim = CylinderSimulator(target_engine)
    points = []
    for rpm in (2500.0, 4000.0, 5500.0):
        cycle = sim.run_cycle(rpm)
        points.append({"rpm": rpm, "power_hp": float(cycle["mean_power_hp"]), "torque_nm": float(cycle["mean_torque_nm"])})

    report = optimize_guided(
        base,
        objective="dataset_error",
        params=["burn_scale", "friction_scale"],
        seed=123,
        max_evals=9,
        target_points=points,
        constraints={"max_signal_mape": {"power_hp": 1.0, "torque_nm": 1.0}},
    )

    assert report.best_candidate["score"] <= report.baseline["score"]
    assert report.optimization_problem["objective"] == "dataset_error"
    assert len(report.candidates) <= 5
    assert report.best_candidate["objective_metrics"]["signal_mape"]["power_hp"] <= report.baseline["objective_metrics"]["signal_mape"]["power_hp"]


@pytest.mark.integration
def test_optimize_guided_peak_power_objective_can_improve_runner_length(tmp_path: Path) -> None:
    base = Engine()
    report = optimize_guided(
        base,
        objective="peak_power",
        params=["intake.runner_length"],
        seed=123,
        max_evals=8,
        rpm_grid=[3000.0, 5000.0, 7000.0],
        param_bounds={"intake.runner_length": (0.20, 0.50)},
        constraints={"min_mean_torque_nm": 10.0},
    )

    assert report.best_candidate["objective_metrics"]["peak_power_hp"] >= report.baseline["objective_metrics"]["peak_power_hp"]
    assert report.best_candidate["params"]["intake.runner_length"] >= 0.20
    assert report.best_candidate["params"]["intake.runner_length"] <= 0.50
