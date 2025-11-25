import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator

ENGINE_CASES = [
    (
        "K20_Sport",
        {
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
                "intake_valve_diameter": 35.0,
                "exhaust_valve_diameter": 30.0,
                "combustion_chamber_vol": 47.6,
                "port_flow_cfm": 290.0,
                "chamber_design": "Pent Roof",
            },
            "camshaft": {
                "intake_lift": 11.5,
                "exhaust_lift": 10.5,
                "intake_duration": 260.0,
                "exhaust_duration": 260.0,
                "lobe_separation": 107.0,
                "advance": 0.0,
            },
            "intake": {
                "runner_length": 230.0,
                "runner_diameter": 48.0,
                "plenum_volume": 3.5,
                "throttle_body_dia": 64.0,
                "throttle_cfm": 850.0,
            },
            "exhaust": {
                "header_primary_length": 450.0,
                "header_primary_diameter": 45.0,
                "collector_length": 150.0,
            },
            "supercharger": {"type": "NA", "boost_pressure_bar": 0.0},
            "friction": {"bottom_end_type": "Performance"},
        },
        8000.0,
        (220.0, 245.0),
        (190.0, 220.0),
    ),
    (
        "V8_Muscle",
        {
            "block": {
                "bore": 101.6,
                "stroke": 88.4,
                "conrod_length": 150.0,
                "num_cylinders": 8,
                "config": "V",
                "bank_angle": 90.0,
                "firing_order": [1, 8, 4, 3, 6, 5, 7, 2],
            },
            "head": {
                "compression_ratio": 10.2,
                "intake_valves": 2,
                "exhaust_valves": 2,
                "intake_valve_diameter": 51.0,
                "exhaust_valve_diameter": 40.0,
                "port_flow_cfm": 230.0,
                "chamber_design": "Typical Wedge",
            },
            "camshaft": {
                "intake_lift": 12.5,
                "exhaust_lift": 12.5,
                "intake_duration": 245.0,
                "exhaust_duration": 245.0,
                "lobe_separation": 108.0,
                "advance": 2.0,
            },
            "intake": {
                "runner_length": 280.0,
                "runner_diameter": 60.0,
                "plenum_volume": 5.0,
                "throttle_body_dia": 75.0,
                "throttle_cfm": 900.0,
            },
            "exhaust": {
                "header_primary_length": 450.0,
                "header_primary_diameter": 45.0,
                "collector_length": 500.0,
            },
            "supercharger": {"type": "NA", "boost_pressure_bar": 0.0},
            "friction": {"bottom_end_type": "Standard"},
        },
        6000.0,
        (350.0, 400.0),
        (400.0, 500.0),
    ),
    (
        "Eco_1600",
        {
            "block": {
                "bore": 79.0,
                "stroke": 81.5,
                "conrod_length": 135.0,
                "num_cylinders": 4,
                "config": "L",
                "bank_angle": 0.0,
                "firing_order": [1, 3, 4, 2],
            },
            "head": {
                "compression_ratio": 9.5,
                "intake_valves": 2,
                "exhaust_valves": 2,
                "intake_valve_diameter": 30.0,
                "exhaust_valve_diameter": 26.0,
                "port_flow_cfm": 160.0,
                "chamber_design": "Pent Roof",
            },
            "camshaft": {
                "intake_lift": 8.5,
                "exhaust_lift": 8.0,
                "intake_duration": 210.0,
                "exhaust_duration": 210.0,
                "lobe_separation": 110.0,
                "advance": 0.0,
            },
            "intake": {
                "runner_length": 320.0,
                "runner_diameter": 40.0,
                "plenum_volume": 2.5,
                "throttle_body_dia": 55.0,
                "throttle_cfm": 400.0,
            },
            "exhaust": {
                "header_primary_length": 400.0,
                "header_primary_diameter": 35.0,
                "collector_length": 400.0,
            },
            "supercharger": {"type": "NA", "boost_pressure_bar": 0.0},
            "friction": {"bottom_end_type": "Standard"},
        },
        6000.0,
        (100.0, 120.0),
        (110.0, 150.0),
    ),
    (
        "Race_V10",
        {
            "block": {
                "bore": 90.0,
                "stroke": 78.0,
                "conrod_length": 150.0,
                "num_cylinders": 10,
                "config": "V",
                "bank_angle": 72.0,
                "firing_order": [1, 6, 5, 10, 2, 7, 3, 8, 4, 9],
            },
            "head": {
                "compression_ratio": 12.5,
                "intake_valves": 2,
                "exhaust_valves": 2,
                "intake_valve_diameter": 37.0,
                "exhaust_valve_diameter": 32.0,
                "port_flow_cfm": 320.0,
                "chamber_design": "Pent Roof",
            },
            "camshaft": {
                "intake_lift": 13.0,
                "exhaust_lift": 13.0,
                "intake_duration": 280.0,
                "exhaust_duration": 280.0,
                "lobe_separation": 110.0,
                "advance": 0.0,
            },
            "intake": {
                "runner_length": 220.0,
                "runner_diameter": 55.0,
                "plenum_volume": 6.0,
                "throttle_body_dia": 70.0,
                "throttle_cfm": 1200.0,
            },
            "exhaust": {
                "header_primary_length": 380.0,
                "header_primary_diameter": 42.0,
                "collector_length": 450.0,
            },
            "supercharger": {"type": "NA", "boost_pressure_bar": 0.0},
            "friction": {"bottom_end_type": "Race"},
        },
        8500.0,
        (500.0, 550.0),
        (400.0, 480.0),
    ),
]


@pytest.mark.integration
@pytest.mark.parametrize("name, config, rpm, hp_range, tq_range", ENGINE_CASES)
def test_engine_output(name, config, rpm, hp_range, tq_range):
    engine = Engine.from_dict(config)
    simulator = CylinderSimulator(engine)

    results = simulator.run_cycle(rpm)
    hp = results["mean_power_hp"]
    tq = results["mean_torque_nm"]
    bmep = results.get("bmep_bar")
    print(
        f"{name:12s} | RPM={rpm:6.0f} | HP={hp:7.2f} | TQ={tq:7.2f} | BMEP={bmep:.2f} bar"
    )

    assert hp_range[0] <= hp <= hp_range[1]
    assert tq_range[0] <= tq <= tq_range[1]
