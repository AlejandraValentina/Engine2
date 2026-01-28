import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.optimize_runner import optimize_runner_length
from core.thermo import CylinderSimulator


def _target_points(engine: Engine, rpm: float) -> list[dict]:
    sim = CylinderSimulator(engine)
    cycle = sim.run_cycle(rpm)
    return [{"rpm": rpm, "power_hp": float(cycle["mean_power_hp"])}]


def test_optimize_deterministic_same_seed_same_result() -> None:
    base = Engine()
    target_engine = Engine.from_dict(base.to_dict())
    target_engine.intake.runner_length *= 1.4

    points = _target_points(target_engine, 3000.0)
    report_a = optimize_runner_length(base, points, bounds_m=(0.2, 0.6), seed=123, max_evals=6)
    report_b = optimize_runner_length(base, points, bounds_m=(0.2, 0.6), seed=123, max_evals=6)

    assert report_a.params_best == report_b.params_best
    assert report_a.error_best == pytest.approx(report_b.error_best)
