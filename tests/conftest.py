import os
import random
from typing import Dict

import pytest

try:
    import numpy as np
except Exception:  # pragma: no cover - numpy may be missing in minimal envs
    np = None

os.environ.setdefault("PYTHONHASHSEED", "0")
random.seed(0)
if np is not None:
    np.random.seed(0)
    # TODO: allow injecting RNG into simulators if they ever use numpy randomness

# Combustion thermal efficiencies are explicitly tuned per fixture to match
# conservative, real-world baselines for each engine archetype.


@pytest.fixture(scope="module")
def k20_config() -> Dict:
    return {
        "block": {
            "bore": 86.0,
            "stroke": 86.0,
            "conrod_length": 139.0,
            "num_cylinders": 4,
            "config": "L",
            "bank_angle": 0.0,
            "firing_order": [1, 3, 4, 2],
            "redline_rpm": 8500.0,
        },
        "head": {
            "compression_ratio": 11.5,
            "intake_valves": 2,
            "exhaust_valves": 2,
            "intake_valve_diameter": 35.0,
            "exhaust_valve_diameter": 30.0,
            "combustion_chamber_vol": 47.6,
            "port_flow_cfm": 290.0,
            "port_flow_efficiency": 0.78,
            "mach_tolerance": 0.85,
            "gasket_thickness_mm": 0.7,
            "gasket_bore_mm": 87.0,
            "deck_clearance_mm": 0.0,
            "piston_dome_cc": 0.0,
            "chamber_design": "Pent Roof",
        },
        "camshaft": {
            "intake_lift": 11.5,
            "exhaust_lift": 10.5,
            "intake_duration": 260.0,
            "exhaust_duration": 260.0,
            "lobe_separation": 107.0,
            "advance": 0.0,
            "peak_rpm": 8000.0,
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
        "simulation_settings": {"ignition_timing_btdc": 30.0},
        "fuel": {"type_name": "Pump Gas", "octane_rating": 93.0, "energy_density": 44e6, "stoich_afr": 14.7},
        "combustion": {
            "thermal_efficiency": 0.55,
            "burn_duration": 40.0,
            "ignition_advance": 30.0,
            "afr": 13.0,
        },
    }


@pytest.fixture(scope="module")
def v8_config() -> Dict:
    return {
        "block": {
            "bore": 101.6,
            "stroke": 88.4,
            "conrod_length": 150.0,
            "num_cylinders": 8,
            "config": "V",
            "bank_angle": 90.0,
            "firing_order": [1, 8, 4, 3, 6, 5, 7, 2],
            "redline_rpm": 6500.0,
        },
        "head": {
            "compression_ratio": 10.2,
            "intake_valves": 2,
            "exhaust_valves": 2,
            "intake_valve_diameter": 51.0,
            "exhaust_valve_diameter": 40.0,
            "combustion_chamber_vol": 80.0,
            "port_flow_cfm": 230.0,
            "port_flow_efficiency": 0.60,
            "mach_tolerance": 0.70,
            "gasket_thickness_mm": 1.0,
            "gasket_bore_mm": 103.0,
            "deck_clearance_mm": 0.1,
            "piston_dome_cc": 0.0,
            "chamber_design": "Typical Wedge",
        },
        "camshaft": {
            "intake_lift": 12.5,
            "exhaust_lift": 12.5,
            "intake_duration": 245.0,
            "exhaust_duration": 245.0,
            "lobe_separation": 108.0,
            "advance": 2.0,
            "peak_rpm": 5200.0,
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
        "simulation_settings": {"ignition_timing_btdc": 30.0},
        "fuel": {"type_name": "Pump Gas", "octane_rating": 93.0, "energy_density": 44e6, "stoich_afr": 14.7},
        "combustion": {
            "thermal_efficiency": 0.50,
            "burn_duration": 55.0,
            "ignition_advance": 28.0,
            "afr": 13.5,
        },
    }


@pytest.fixture(scope="module")
def eco_config() -> Dict:
    return {
        "block": {
            "bore": 79.0,
            "stroke": 81.5,
            "conrod_length": 135.0,
            "num_cylinders": 4,
            "config": "L",
            "bank_angle": 0.0,
            "firing_order": [1, 3, 4, 2],
            "redline_rpm": 6500.0,
        },
        "head": {
            "compression_ratio": 9.5,
            "intake_valves": 2,
            "exhaust_valves": 2,
            "intake_valve_diameter": 30.0,
            "exhaust_valve_diameter": 26.0,
            "combustion_chamber_vol": 46.0,
            "port_flow_cfm": 160.0,
            "port_flow_efficiency": 0.55,
            "mach_tolerance": 0.65,
            "gasket_thickness_mm": 1.0,
            "gasket_bore_mm": 80.0,
            "deck_clearance_mm": 0.1,
            "piston_dome_cc": 0.0,
            "chamber_design": "Pent Roof",
        },
        "camshaft": {
            "intake_lift": 8.5,
            "exhaust_lift": 8.0,
            "intake_duration": 210.0,
            "exhaust_duration": 210.0,
            "lobe_separation": 110.0,
            "advance": 0.0,
            "peak_rpm": 4500.0,
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
        "simulation_settings": {"ignition_timing_btdc": 30.0},
        "fuel": {"type_name": "Pump Gas", "octane_rating": 93.0, "energy_density": 44e6, "stoich_afr": 14.7},
        "combustion": {
            "thermal_efficiency": 0.48,
            "burn_duration": 65.0,
            "ignition_advance": 25.0,
            "afr": 14.2,
        },
    }


@pytest.fixture(scope="module")
def v10_config() -> Dict:
    return {
        "block": {
            "bore": 90.0,
            "stroke": 78.0,
            "conrod_length": 150.0,
            "num_cylinders": 10,
            "config": "V",
            "bank_angle": 72.0,
            "firing_order": [1, 6, 5, 10, 2, 7, 3, 8, 4, 9],
            "redline_rpm": 9000.0,
        },
        "head": {
            "compression_ratio": 12.5,
            "intake_valves": 2,
            "exhaust_valves": 2,
            "intake_valve_diameter": 37.0,
            "exhaust_valve_diameter": 32.0,
            "combustion_chamber_vol": 40.0,
            "port_flow_cfm": 320.0,
            "port_flow_efficiency": 0.82,
            "mach_tolerance": 0.90,
            "gasket_thickness_mm": 0.9,
            "gasket_bore_mm": 92.0,
            "deck_clearance_mm": 0.05,
            "piston_dome_cc": 0.0,
            "chamber_design": "Pent Roof",
        },
        "camshaft": {
            "intake_lift": 13.0,
            "exhaust_lift": 13.0,
            "intake_duration": 280.0,
            "exhaust_duration": 280.0,
            "lobe_separation": 110.0,
            "advance": 0.0,
            "peak_rpm": 8800.0,
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
        "simulation_settings": {"ignition_timing_btdc": 30.0},
        "fuel": {"type_name": "Pump Gas", "octane_rating": 100.0, "energy_density": 44e6, "stoich_afr": 14.7},
        "combustion": {
            "thermal_efficiency": 0.58,
            "burn_duration": 35.0,
            "ignition_advance": 32.0,
            "afr": 12.8,
        },
    }


@pytest.fixture(scope="module")
def f1_v12_config() -> Dict:
    return {
        "block": {
            "bore": 96.0,
            "stroke": 34.5,
            "conrod_length": 110.0,
            "num_cylinders": 12,
            "config": "V",
            "bank_angle": 60.0,
            "firing_order": [1, 7, 5, 11, 3, 9, 6, 12, 2, 8, 4, 10],
            "redline_rpm": 18000.0,
        },
        "head": {
            "compression_ratio": 13.5,
            "intake_valves": 2,
            "exhaust_valves": 2,
            "intake_valve_diameter": 36.0,
            "exhaust_valve_diameter": 30.0,
            "combustion_chamber_vol": 28.0,
            "port_flow_cfm": 420.0,
            "port_flow_efficiency": 0.92,
            "mach_tolerance": 0.85,
            "gasket_thickness_mm": 0.8,
            "gasket_bore_mm": 97.0,
            "deck_clearance_mm": 0.05,
            "piston_dome_cc": 0.0,
            "chamber_design": "Pent Roof",
        },
        "camshaft": {
            "intake_lift": 14.5,
            "exhaust_lift": 14.0,
            "intake_duration": 300.0,
            "exhaust_duration": 300.0,
            "lobe_separation": 110.0,
            "advance": 0.0,
            "peak_rpm": 17000.0,
        },
        "intake": {
            "runner_length": 180.0,
            "runner_diameter": 45.0,
            "plenum_volume": 5.0,
            "throttle_body_dia": 70.0,
            "throttle_cfm": 1500.0,
        },
        "exhaust": {
            "header_primary_length": 350.0,
            "header_primary_diameter": 38.0,
            "collector_length": 400.0,
        },
        "supercharger": {"type": "NA", "boost_pressure_bar": 0.0},
        "friction": {"bottom_end_type": "Race"},
        "simulation_settings": {"ignition_timing_btdc": 35.0},
        "fuel": {"type_name": "Race Gas", "octane_rating": 110.0, "energy_density": 44e6, "stoich_afr": 14.7},
        "combustion": {
            "thermal_efficiency": 0.58,
            "burn_duration": 35.0,
            "ignition_advance": 35.0,
            "afr": 12.6,
        },
    }


@pytest.fixture(scope="module")
def kart_125_config() -> Dict:
    return {
        "block": {
            "bore": 54.0,
            "stroke": 54.0,
            "conrod_length": 110.0,
            "num_cylinders": 1,
            "config": "L",
            "bank_angle": 0.0,
            "firing_order": [1],
            "redline_rpm": 11000.0,
        },
        "head": {
            "compression_ratio": 12.0,
            "intake_valves": 2,
            "exhaust_valves": 2,
            "intake_valve_diameter": 28.0,
            "exhaust_valve_diameter": 24.0,
            "combustion_chamber_vol": 12.0,
            "port_flow_cfm": 120.0,
            "port_flow_efficiency": 0.70,
            "mach_tolerance": 0.80,
            "gasket_thickness_mm": 0.7,
            "gasket_bore_mm": 55.0,
            "deck_clearance_mm": 0.05,
            "piston_dome_cc": 0.0,
            "chamber_design": "Pent Roof",
        },
        "camshaft": {
            "intake_lift": 9.5,
            "exhaust_lift": 9.0,
            "intake_duration": 240.0,
            "exhaust_duration": 240.0,
            "lobe_separation": 108.0,
            "advance": 0.0,
            "peak_rpm": 10500.0,
        },
        "intake": {
            "runner_length": 200.0,
            "runner_diameter": 30.0,
            "plenum_volume": 0.8,
            "throttle_body_dia": 28.0,
            "throttle_cfm": 150.0,
        },
        "exhaust": {
            "header_primary_length": 300.0,
            "header_primary_diameter": 30.0,
            "collector_length": 350.0,
        },
        "supercharger": {"type": "NA", "boost_pressure_bar": 0.0},
        "friction": {"bottom_end_type": "Performance"},
        "simulation_settings": {"ignition_timing_btdc": 28.0},
        "fuel": {"type_name": "Pump Gas", "octane_rating": 95.0, "energy_density": 44e6, "stoich_afr": 14.7},
        "combustion": {
            "thermal_efficiency": 0.50,
            "burn_duration": 50.0,
            "ignition_advance": 28.0,
            "afr": 13.5,
        },
    }
