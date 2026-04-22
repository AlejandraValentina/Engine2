import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import muscl_hancock_step


def _pressure_from_state(U: np.ndarray, gamma: float) -> np.ndarray:
    rho = U[:, 0]
    u = U[:, 1] / np.maximum(rho, 1e-12)
    return (gamma - 1.0) * (U[:, 2] - 0.5 * rho * u * u)


def _run_pulse_case(cells: int) -> float:
    gamma = 1.4
    gas_constant = 287.0
    length = 1.0
    dx = length / cells

    rho0 = 1.2
    T0 = 300.0
    p0 = rho0 * gas_constant * T0
    u0 = 0.0
    E0 = gas_constant * T0 / (gamma - 1.0)

    U = np.zeros((cells + 2, 4))
    U[1:-1, 0] = rho0
    U[1:-1, 1] = rho0 * u0
    U[1:-1, 2] = rho0 * (E0 + 0.5 * u0 * u0)
    U[1:-1, 3] = rho0 * 0.2
    U[0] = U[1]
    U[-1] = U[-2]

    # Small pressure pulse near the inlet; we measure reflected amplitude near the outlet.
    U[3, 2] *= 1.2

    a0 = np.sqrt(gamma * gas_constant * T0)
    dt = 0.4 * dx / a0
    steps = int(2.0 * length / (a0 * dt))

    peak = 0.0
    t_start = length / a0
    for step in range(steps):
        U = muscl_hancock_step(U, dx, dt, gamma, gas_constant, p_outlet=p0)
        if step * dt < t_start:
            continue
        p_probe = _pressure_from_state(U[1:-1], gamma)[-3]
        peak = max(peak, abs(p_probe - p0))
    return float(peak)


def test_non_reflecting_outlet_refinement_reduces_local_sensitivity() -> None:
    coarse_peak = _run_pulse_case(40)
    medium_peak = _run_pulse_case(80)
    fine_peak = _run_pulse_case(120)

    # This is a local resolution-sensitivity smoke, not a formal grid-convergence proof.
    assert coarse_peak > medium_peak > fine_peak
    assert fine_peak > 0.0

