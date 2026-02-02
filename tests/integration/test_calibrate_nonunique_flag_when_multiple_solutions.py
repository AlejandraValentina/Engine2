import pytest

from core.auto_calibration import calibrate_engine_diagnostics
from core.engine_components import Engine


@pytest.mark.integration
def test_calibrate_nonunique_flag_when_multiple_solutions() -> None:
    engine = Engine()
    points = [
        {"rpm": 3000, "power_hp": 120.0},
    ]

    report = calibrate_engine_diagnostics(
        engine,
        points,
        ["ve_scale", "friction_scale"],
        max_evals=15,
        multi_start=1,
        top_k=5,
        seed=1,
        eps_obj=1e6,
        eps_params=0.05,
    )

    assert report["uniqueness"]["unique"] is False
    assert report["uniqueness"]["reason"] == "non_identifiable"
