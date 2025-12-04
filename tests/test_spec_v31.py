import math

import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine, Pipe
from core import numerics
from core.thermo import CylinderSimulator
from core.simulator import Engine1DSolver


def test_mach_uses_dynamic_speed_of_sound():
    engine = Engine()
    engine.simulation_settings.air_temperature_c = 50.0
    sim = CylinderSimulator(engine)
    gamma_air = engine.simulation_settings.gamma_air
    R = engine.simulation_settings.gas_constant_R
    T = (engine.simulation_settings.air_temperature_c) + 273.15
    expected_c = math.sqrt(gamma_air * R * T)
    bore_m = engine.block.bore * 1e-3
    piston_speed = 20.0
    Ap = math.pi * (bore_m / 2.0) ** 2
    valve_dia_m = engine.head.intake_valve_diameter_mm * 1e-3
    eff = engine.head.port_flow_efficiency
    Av = engine.head.intake_valves * math.pi * (valve_dia_m / 2.0) ** 2 * eff
    expected_mach = (piston_speed * (Ap / Av)) / expected_c
    ve, mach = sim._calculate_dynamic_ve(3000.0, piston_speed, bore_m, 260.0, gamma_air, R, T)
    assert math.isclose(mach, expected_mach, rel_tol=1e-3)
    assert 0.0 < ve <= 1.5


def test_backpressure_factor_applied():
    engine = Engine()
    engine.simulation_settings.exhaust_backpressure_factor = 1.2
    sim = CylinderSimulator(engine)
    result = sim.run_cycle(3000.0)
    pressure = result["pressure"]
    expected = engine.simulation_settings.exhaust_backpressure_factor * engine.simulation_settings.air_pressure_bar * 100000.0
    assert np.isclose(np.max(pressure[-50:]), expected, rtol=1e-3)


def test_nozzle_choking_criterion():
    p_up = 200000.0
    T_up = 300.0
    area = 0.0005
    sub_ratio = numerics.calculate_mass_flow_rate(p_up, 120000.0, T_up, area, 0.9)
    choked_ratio = numerics.calculate_mass_flow_rate(p_up, 50000.0, T_up, area, 0.9)
    assert choked_ratio >= sub_ratio


def test_outlet_bc_ghost_state(tmp_path):
    pipe = Engine().exhaust  # dimensions not used, placeholder
    primary = Pipe(length=1.0, diameter_inlet=0.04, diameter_outlet=0.04, wall_temperature=600.0, friction_coeff=0.02)
    tail = Pipe(length=1.0, diameter_inlet=0.05, diameter_outlet=0.05, wall_temperature=600.0, friction_coeff=0.02)
    solver = Engine1DSolver([primary], tail, [1], p_atm=101325.0, T_amb=300.0)
    tail_state = solver.tail_state
    tail_state["U"][-2, 1] = 10.0  # small positive momentum
    solver._tail_atmosphere()
    ghost = tail_state["U"][-1]
    assert math.isclose(ghost[1] / ghost[0], tail_state["U"][-2, 1] / tail_state["U"][-2, 0], rel_tol=1e-6)
    assert ghost[0] > 0.0 and ghost[2] >= 0.0


def test_power_torque_identity():
    engine = Engine()
    sim = CylinderSimulator(engine)
    result = sim.run_cycle(3000.0)
    torque = result["mean_torque_nm"]
    omega = 3000.0 * 2.0 * math.pi / 60.0
    expected_hp = (torque * omega) / 745.7
    assert math.isclose(expected_hp, result["mean_power_hp"], rel_tol=1e-2)

