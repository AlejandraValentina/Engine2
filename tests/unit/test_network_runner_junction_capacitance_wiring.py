import numpy as np

from core.engine_components import Pipe, SimulationSettings
from core.simulator import Engine1DSolver, _pressure_from_state


def _make_U(p: float, T: float, u: float, gamma: float, gas_constant: float) -> np.ndarray:
    rho = p / (gas_constant * max(T, 1.0))
    e_int = p / max((gamma - 1.0) * rho, 1e-12)
    E_tot = e_int + 0.5 * u * u
    return np.array([rho, rho * u, rho * E_tot], dtype=np.float64)


def _build_solver(settings: SimulationSettings, n_primaries: int = 4) -> Engine1DSolver:
    primaries = [
        Pipe(length=200.0, diameter_inlet=40.0, diameter_outlet=40.0)
        for _ in range(n_primaries)
    ]
    tail = Pipe(length=300.0, diameter_inlet=40.0, diameter_outlet=40.0)
    firing_order = list(range(1, n_primaries + 1))
    return Engine1DSolver(
        primaries,
        tail,
        firing_order=firing_order,
        target_dx=0.05,
        settings=settings,
    )


def _seed_pulse(solver: Engine1DSolver, p_high: float, u_pulse: float) -> None:
    base = _make_U(solver.p_atm, solver.T_amb, 0.0, solver.gamma, solver.gas_constant)
    for state in solver.primary_states:
        state["U"][-2] = base.copy()
    solver.primary_states[0]["U"][-2] = _make_U(
        p_high, solver.T_amb, u_pulse, solver.gamma, solver.gas_constant
    )
    solver.tail_state["U"][1] = base.copy()


def _tail_pressure_trace(solver: Engine1DSolver, steps: int, dt: float) -> np.ndarray:
    pressures = []
    for _ in range(steps):
        solver.step(
            rpm=0.0,
            dt=dt,
            exhaust_open_start=0.0,
            exhaust_open_end=0.0,
            p_exhaust=solver.p_atm,
            T_exhaust=solver.T_amb,
        )
        p_tail = _pressure_from_state(
            solver.tail_state["U"][1:2],
            solver.settings.clamp_p_min,
            solver.settings.clamp_p_max,
            solver.gamma,
            solver.settings.clamp_rho_min,
        )[0]
        pressures.append(p_tail)
    return np.asarray(pressures, dtype=np.float64)


def test_network_runner_junction_capacitance_wiring() -> None:
    dt = 1e-5
    steps = 25

    base_settings = SimulationSettings()
    solver_base = _build_solver(base_settings)
    _seed_pulse(solver_base, p_high=1.2 * solver_base.p_atm, u_pulse=40.0)
    base_trace = _tail_pressure_trace(solver_base, steps, dt)

    disabled_settings = SimulationSettings(
        junction_capacitance={"enabled": False, "volume_m3": 0.01},
        junction_losses={"enabled": False, "default_k": 1.0},
    )
    solver_disabled = _build_solver(disabled_settings)
    _seed_pulse(solver_disabled, p_high=1.2 * solver_disabled.p_atm, u_pulse=40.0)
    disabled_trace = _tail_pressure_trace(solver_disabled, steps, dt)

    assert np.allclose(base_trace, disabled_trace, rtol=0.0, atol=1e-12)

    cap_settings = SimulationSettings(
        junction_capacitance={
            "enabled": True,
            "volume_m3": 0.01,
            "under_relax_alpha": 0.7,
        },
        junction_losses={
            "enabled": True,
            "default_k": 1.0,
        },
    )
    solver_cap = _build_solver(cap_settings)
    _seed_pulse(solver_cap, p_high=1.2 * solver_cap.p_atm, u_pulse=40.0)
    cap_trace = _tail_pressure_trace(solver_cap, steps, dt)

    assert np.all(np.isfinite(base_trace))
    assert np.all(np.isfinite(cap_trace))

    peak_base = float(np.max(base_trace) - np.min(base_trace))
    peak_cap = float(np.max(cap_trace) - np.min(cap_trace))
    assert peak_base > 0.0
    assert peak_cap < 0.9 * peak_base

    cap_state = solver_cap.junction_capacitance_state
    assert cap_state is not None
    assert np.isfinite(cap_state.p)
    assert np.isfinite(cap_state.T)
    assert cap_state.m_total > 0.0
    assert 0.0 <= cap_state.Y <= 1.0
