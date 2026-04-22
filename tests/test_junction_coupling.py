import math

import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Pipe, SimulationSettings
from core.simulator import Engine1DSolver


def _make_U(p: float, T: float, u: float, gamma: float, gas_constant: float) -> np.ndarray:
    rho = p / (gas_constant * max(T, 1.0))
    e_int = p / max((gamma - 1.0) * rho, 1e-12)
    E_tot = e_int + 0.5 * u * u
    return np.array([rho, rho * u, rho * E_tot], dtype=np.float64)


def _build_solver(settings: SimulationSettings) -> Engine1DSolver:
    primary = Pipe(length=200.0, diameter_inlet=40.0, diameter_outlet=40.0)
    tail = Pipe(length=200.0, diameter_inlet=40.0, diameter_outlet=40.0)
    return Engine1DSolver([primary], tail, firing_order=[1], settings=settings)


def test_collector_pressure_rises_with_inflow():
    settings = SimulationSettings()
    solver = _build_solver(settings)

    p_high = 2.0 * solver.p_atm
    primary = solver.primary_states[0]
    primary["U"][-2] = _make_U(p_high, solver.T_amb, 50.0, solver.gamma, solver.gas_constant)

    tail = solver.tail_state
    tail["U"][1] = _make_U(solver.p_atm, solver.T_amb, 0.0, solver.gamma, solver.gas_constant)

    p_before = solver.collector.pressure
    solver.step(
        rpm=0.0,
        dt=1e-4,
        exhaust_open_start=0.0,
        exhaust_open_end=0.0,
        p_exhaust=solver.p_atm,
        T_exhaust=solver.T_amb,
    )

    assert solver.collector.pressure > p_before


def test_no_flow_when_balanced():
    settings = SimulationSettings()
    solver = _build_solver(settings)

    primary = solver.primary_states[0]
    balanced = _make_U(solver.p_atm, solver.T_amb, 0.0, solver.gamma, solver.gas_constant)
    primary["U"][-2] = balanced

    tail = solver.tail_state
    tail["U"][1] = balanced

    p_before = solver.collector.pressure
    solver.step(
        rpm=0.0,
        dt=1e-4,
        exhaust_open_start=0.0,
        exhaust_open_end=0.0,
        p_exhaust=solver.p_atm,
        T_exhaust=solver.T_amb,
    )

    assert math.isclose(solver.collector.pressure, p_before, rel_tol=1e-4)


def test_collector_temperature_increases_with_hot_inflow():
    settings = SimulationSettings()
    solver = _build_solver(settings)

    T_hot = 800.0
    primary = solver.primary_states[0]
    primary["U"][-2] = _make_U(solver.p_atm, T_hot, 80.0, solver.gamma, solver.gas_constant)

    tail = solver.tail_state
    tail["U"][1] = _make_U(solver.p_atm, solver.T_amb, 0.0, solver.gamma, solver.gas_constant)

    T_before = solver.collector.temperature
    solver.step(
        rpm=0.0,
        dt=1e-4,
        exhaust_open_start=0.0,
        exhaust_open_end=0.0,
        p_exhaust=solver.p_atm,
        T_exhaust=solver.T_amb,
    )

    assert solver.collector.temperature > T_before
