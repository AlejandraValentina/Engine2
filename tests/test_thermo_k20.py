import numpy as np
import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def build_k20_engine(comb_chamber_vol=None) -> Engine:
    """Create a representative K20-style engine configuration."""
    config = {
        "block": {
            "bore": 86.0,
            "stroke": 86.0,
            "conrod_length": 143.0,
            "num_cylinders": 4,
            "redline_rpm": 8600.0,
        },
        "head": {
            "compression_ratio": 11.0,
            "intake_valves": 2,
            "exhaust_valves": 2,
            "combustion_chamber_vol": comb_chamber_vol,
            "port_flow_cfm": 260.0,
        },
        # Use "cam" to validate backward-compatible loading
        "cam": {
            "intake_lift": 13.0,
            "exhaust_lift": 12.0,
            "intake_duration": 270.0,
            "exhaust_duration": 270.0,
            "lobe_separation": 108.0,
            "advance": 2.0,
        },
        "intake": {
            "runner_length": 280.0,
            "runner_diameter": 48.0,
            "plenum_volume": 4.5,
            "throttle_body_dia": 70.0,
            "throttle_cfm": 600.0,
        },
        "exhaust": {
            "header_primary_length": 420.0,
            "header_primary_diameter": 40.0,
            "collector_length": 500.0,
        },
        "supercharger": {"type": "NA", "boost_pressure_bar": 0.0},
    }
    return Engine.from_dict(config)


def test_run_cycle_no_nan():
    engine = build_k20_engine(comb_chamber_vol=47.0)
    sim = CylinderSimulator(engine)
    results = sim.run_cycle(6000.0)
    assert np.isfinite(results["pressure"]).all()
    assert np.isfinite(results["torque"]).all()
    assert np.min(results["volume"]) > 0.0


@pytest.mark.parametrize("rpm", [2000.0, 4000.0, 6000.0, 8000.0])
def test_mean_outputs_finite(rpm):
    engine = build_k20_engine(comb_chamber_vol=47.0)
    sim = CylinderSimulator(engine)
    results = sim.run_cycle(rpm)
    assert np.isfinite(results["mean_power_hp"])
    assert np.isfinite(results["mean_torque_nm"])


def test_combustion_chamber_zero_treated_as_fallback():
    engine = build_k20_engine(comb_chamber_vol=0.0)
    sim = CylinderSimulator(engine)
    results = sim.run_cycle(6000.0)
    assert np.isfinite(results["pressure"]).all()
    assert np.min(results["volume"]) > 0.0
