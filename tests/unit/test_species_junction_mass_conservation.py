import pytest

np = pytest.importorskip("numpy")

from core.advanced.junctions import junction_leg_flux
from core.engine_components import Pipe, SimulationSettings
from core.simulator import Engine1DSolver


def _set_cell(U: np.ndarray, idx: int, p: float, T: float, u: float, gamma: float, gas_constant: float, Y: float) -> None:
    rho = p / (gas_constant * max(T, 1.0))
    e_int = p / max((gamma - 1.0) * rho, 1e-12)
    E_tot = e_int + 0.5 * u * u
    U[idx, 0] = rho
    U[idx, 1] = rho * u
    U[idx, 2] = rho * E_tot
    U[idx, 3] = rho * Y


def test_species_junction_mass_conservation() -> None:
    settings = SimulationSettings()
    settings.species.enabled = True
    settings.junction_capacitance = {
        "enabled": True,
        "volume_m3": 0.01,
        "p_init_pa": 101325.0,
        "t_init_k": 350.0,
        "y_init": 0.1,
    }

    primary_a = Pipe(length=200.0, diameter_inlet=40.0, diameter_outlet=40.0)
    primary_b = Pipe(length=200.0, diameter_inlet=40.0, diameter_outlet=40.0)
    tail = Pipe(length=200.0, diameter_inlet=45.0, diameter_outlet=45.0)

    solver = Engine1DSolver(
        [primary_a, primary_b],
        tail,
        firing_order=[1, 2],
        settings=settings,
        p_atm=101325.0,
        T_amb=300.0,
    )
    assert solver.junction_capacitance_state is not None

    gamma = solver.gamma
    gas_constant = solver.gas_constant

    _set_cell(solver.primary_states[0]["U"], -2, 150000.0, 600.0, 20.0, gamma, gas_constant, 0.2)
    _set_cell(solver.primary_states[1]["U"], -2, 140000.0, 500.0, 15.0, gamma, gas_constant, 0.8)
    _set_cell(solver.tail_state["U"], 1, 80000.0, 400.0, 5.0, gamma, gas_constant, 0.4)

    cp = gamma * gas_constant / max(gamma - 1.0, 1e-9)
    cp_model = getattr(settings, "cp_model", "constant")
    junction_state = solver.junction_capacitance_state

    leg_fluxes = []
    for idx, state in enumerate(solver.primary_states):
        prim = solver._pipe_primitive(state["U"][-2])
        area_face = float(state["areas"][-1])
        mdot, Hdot, Ydot, _, _ = junction_leg_flux(
            prim,
            area_face,
            junction_state,
            gamma,
            gas_constant,
            cp,
            cp_model=cp_model,
            leg_id=f"cyl{idx+1}",
            loss_cfg=solver.junction_losses_cfg,
        )
        leg_fluxes.append((mdot, Hdot, Ydot))

    prim_tail = solver._pipe_primitive(solver.tail_state["U"][1])
    area_tail = float(solver.tail_state["areas"][0])
    mdot_tail, Hdot_tail, Ydot_tail, _, _ = junction_leg_flux(
        prim_tail,
        area_tail,
        junction_state,
        gamma,
        gas_constant,
        cp,
        cp_model=cp_model,
        leg_id="tail",
        loss_cfg=solver.junction_losses_cfg,
    )
    leg_fluxes.append((mdot_tail, Hdot_tail, Ydot_tail))

    mdot_in = 0.0
    Ydot_in = 0.0
    mdot_out = 0.0
    Ydot_out = 0.0
    for mdot, _, Ydot in leg_fluxes:
        if mdot >= 0.0:
            mdot_in += mdot
            Ydot_in += Ydot
        else:
            mdot_out += -mdot
            Ydot_out += -Ydot

    dt = 1e-4
    m_total_before = junction_state.m_total
    mY_before = junction_state.mY

    expected_m_total = m_total_before + (mdot_in - mdot_out) * dt
    expected_mY = mY_before + (Ydot_in - Ydot_out) * dt
    expected_Y = expected_mY / max(expected_m_total, 1e-12)
    expected_Y = float(min(max(expected_Y, 0.0), 1.0))
    expected_mY = expected_Y * expected_m_total

    solver._apply_junction_capacitance(dt)

    assert solver.junction_capacitance_state is not None
    assert solver.junction_capacitance_state.mY == pytest.approx(expected_mY, rel=1e-6, abs=1e-9)
    assert solver.junction_capacitance_state.Y == pytest.approx(expected_Y, rel=1e-6)
