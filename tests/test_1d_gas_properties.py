import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Pipe, SimulationSettings
from core.simulator import Engine1DSolver, _pressure_from_state


def test_custom_gamma_and_gas_constant_drive_initial_state():
    settings = SimulationSettings(gamma_exhaust=1.3, gas_constant_R=300.0)
    primary = Pipe(length=100.0, diameter_inlet=50.0, diameter_outlet=50.0)
    tail = Pipe(length=150.0, diameter_inlet=60.0, diameter_outlet=60.0)

    solver = Engine1DSolver(
        [primary],
        tail,
        firing_order=[1],
        target_dx=0.1,
        p_atm=101325.0,
        T_amb=290.0,
        settings=settings,
    )

    state = solver.primary_states[0]
    rho_expected = 101325.0 / (settings.gas_constant_R * 290.0)
    assert state["U"][0, 0] == pytest.approx(rho_expected)

    p_calc = _pressure_from_state(state["U"], 0.0, 1e9, solver.gamma)[0]
    assert p_calc == pytest.approx(101325.0)

    assert solver.gamma == pytest.approx(settings.gamma_exhaust)
