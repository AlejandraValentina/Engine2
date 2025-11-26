import copy
import numpy as np
import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator

K20_CONFIG = {
    "block": {
        "bore": 86.0,
        "stroke": 86.0,
        "conrod_length": 139.0,
        "num_cylinders": 4,
        "config": "L",
        "bank_angle": 0.0,
        "firing_order": [1, 3, 4, 2],
    },
    "head": {
        "compression_ratio": 11.5,
        "intake_valves": 2,
        "exhaust_valves": 2,
        "combustion_chamber_vol": 47.6,
    },
    # Using legacy "cam" key to verify backward compatibility
    "cam": {
        "intake_lift": 11.5,
        "exhaust_lift": 10.5,
        "intake_duration": 265.0,
        "exhaust_duration": 260.0,
        "lobe_separation": 107.0,
        "advance": 0.0,
    },
    "intake": {
        "runner_length": 230.0,
        "runner_diameter": 48.0,
        "plenum_volume": 3.5,
        "throttle_body_dia": 64.0,
    },
    "exhaust": {
        "header_primary_length": 450.0,
        "header_primary_diameter": 45.0,
        "collector_length": 150.0,
    },
    "supercharger": {"type": "NA", "boost_pressure_bar": 0.0},
}


def build_engine(comb_chamber_vol=None) -> Engine:
    config = copy.deepcopy(K20_CONFIG)
    if comb_chamber_vol is not None:
        config["head"]["combustion_chamber_vol"] = comb_chamber_vol
    return Engine.from_dict(config)


def test_run_cycle_no_nan():
    engine = build_engine()
    sim = CylinderSimulator(engine)
    results = sim.run_cycle(6000.0)
    assert np.isfinite(results["pressure"]).all()
    assert np.isfinite(results["torque"]).all()
    assert np.min(results["volume"]) > 0.0


@pytest.mark.parametrize("rpm", [2000.0, 4000.0, 6000.0, 8000.0])
def test_mean_outputs_finite(rpm):
    engine = build_engine()
    sim = CylinderSimulator(engine)
    results = sim.run_cycle(rpm)
    assert np.isfinite(results["mean_power_hp"])
    assert np.isfinite(results["mean_torque_nm"])


def test_combustion_chamber_zero_fallback():
    engine = build_engine(comb_chamber_vol=0.0)
    sim = CylinderSimulator(engine)
    results = sim.run_cycle(6000.0)
    assert np.isfinite(results["pressure"]).all()
    assert np.min(results["volume"]) > 0.0
