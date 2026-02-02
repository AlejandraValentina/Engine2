import pytest

from core.auto_calibration import _apply_scales, calibrate_engine_diagnostics
from core.engine_components import Engine
from core.thermo import CylinderSimulator


@pytest.mark.integration
def test_calibrate_unique_solution_recovers_params() -> None:
    engine = Engine()
    target_engine = Engine.from_dict(engine.to_dict())
    target_params = {"friction_scale": 0.8}
    _apply_scales(target_engine, target_params)

    sim = CylinderSimulator(target_engine)
    points = []
    for rpm in (3000, 6000):
        cycle = sim.run_cycle(float(rpm))
        points.append(
            {
                "rpm": float(rpm),
                "torque_nm": float(cycle["mean_torque_nm"]),
                "power_hp": float(cycle["mean_power_hp"]),
            }
        )

    report = calibrate_engine_diagnostics(
        engine,
        points,
        ["friction_scale"],
        max_evals=20,
        multi_start=1,
        top_k=5,
        seed=0,
        eps_obj=1e-6,
        eps_params=0.02,
    )

    best = report["best_solution"]["params"]
    assert best["friction_scale"] == pytest.approx(0.8, rel=1e-6, abs=1e-6)
    assert report["uniqueness"]["unique"] is True
