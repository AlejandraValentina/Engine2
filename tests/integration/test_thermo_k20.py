import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator
from core.units import bar_to_pa

pytestmark = [pytest.mark.slow]

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
    settings = engine.simulation_settings
    assert (
        not settings.enable_0d_to_1d_exhaust_coupling
    ), "0D->1D coupling must be disabled by default"
    assert 0.8 <= settings.air_pressure_bar <= 1.2, f"air_pressure_bar={settings.air_pressure_bar}"
    ambient_pressure_pa = bar_to_pa(settings.air_pressure_bar)
    assert 8.0e4 <= ambient_pressure_pa <= 1.2e5, f"ambient_pressure_pa={ambient_pressure_pa:.1f}"
    ambient_temp_k = settings.air_temperature_c + 273.15
    assert 200.0 <= ambient_temp_k <= 400.0, f"ambient_temp_k={ambient_temp_k:.1f}"

    simulator = CylinderSimulator(engine)

    results_8000 = simulator.run_cycle(8000.0)
    hp_8000 = results_8000["mean_power_hp"]
    assert 115.0 <= hp_8000 <= 140.0, f"hp_8000={hp_8000:.2f} expected [115, 140]"

    results_6000 = simulator.run_cycle(6000.0)
    tq_6000 = results_6000["mean_torque_nm"]
    assert 145.0 <= tq_6000 <= 170.0, f"tq_6000={tq_6000:.2f} expected [145, 170]"
