import numpy as np

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def test_0d_cycle_contract():
    engine = Engine()
    sim = CylinderSimulator(engine)

    results = sim.run_cycle(3000.0)

    expected_keys = {
        "mean_power_hp",
        "mean_torque_nm",
        "bmep_bar",
        "ve",
        "ve_actual",
        "mach_index",
        "friction_hp",
        "knock_warning",
    }
    assert expected_keys.issubset(results.keys())

    scalars = [
        results["mean_power_hp"],
        results["mean_torque_nm"],
        results["bmep_bar"],
        results["ve"],
        results["ve_actual"],
        results["mach_index"],
        results["friction_hp"],
    ]
    assert all(np.isfinite(v) for v in scalars)
    assert results["mean_power_hp"] >= 0.0
    assert results["mean_torque_nm"] >= 0.0
    assert 0.0 <= results["ve"] <= 200.0
    assert 0.0 <= results["ve_actual"] <= 2.0
    assert results["bmep_bar"] >= 0.0
    assert isinstance(results["knock_warning"], (bool, np.bool_))

    # Arrays should be finite and non-empty
    for key in ("angle", "pressure", "volume", "torque"):
        arr = results[key]
        assert arr.size > 0
        assert np.isfinite(arr).all()
