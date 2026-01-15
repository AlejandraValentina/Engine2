import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator

pytestmark = pytest.mark.legacy

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
        "port_flow_cfm": 280.0,
    },
    "camshaft": {
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


@pytest.mark.integration
def test_k20_performance():
    engine = Engine.from_dict(K20_CONFIG)
    simulator = CylinderSimulator(engine)

    results_8000 = simulator.run_cycle(8000.0)
    hp_8000 = results_8000["mean_power_hp"]
    assert 200.0 <= hp_8000 <= 230.0

    results_6000 = simulator.run_cycle(6000.0)
    tq_6000 = results_6000["mean_torque_nm"]
    assert 195.0 <= tq_6000 <= 215.0
