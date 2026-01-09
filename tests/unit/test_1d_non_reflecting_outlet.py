import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import muscl_hancock_step


def _pressure_from_state(U: np.ndarray, gamma: float) -> np.ndarray:
    rho = U[:, 0]
    u = U[:, 1] / np.maximum(rho, 1e-12)
    return (gamma - 1.0) * (U[:, 2] - 0.5 * rho * u * u)


def test_non_reflecting_outlet_reduces_reflection() -> None:
    gamma = 1.4
    R = 287.0
    cells = 80
    length = 1.0
    dx = length / cells

    rho0 = 1.2
    T0 = 300.0
    p0 = rho0 * R * T0
    u0 = 0.0
    E0 = R * T0 / (gamma - 1.0)

    U0 = np.zeros((cells, 4))
    U0[:, 0] = rho0
    U0[:, 1] = rho0 * u0
    U0[:, 2] = rho0 * (E0 + 0.5 * u0 * u0)
    U0[:, 3] = rho0 * 0.2

    U0[2, 2] *= 1.2

    a0 = np.sqrt(gamma * R * T0)
    dt = 0.4 * dx / a0
    steps = int(2.0 * length / (a0 * dt))

    def run_case(p_outlet: float | None) -> float:
        U = U0.copy()
        peak = 0.0
        t_start = length / a0
        for step in range(steps):
            U = muscl_hancock_step(U, dx, dt, gamma, R, p_outlet=p_outlet)
            if step * dt < t_start:
                continue
            p_probe = _pressure_from_state(U, gamma)[-3]
            peak = max(peak, p_probe - p0)
        return peak

    peak_copy = run_case(None)
    peak_non_reflect = run_case(p0)

    assert peak_copy > 0.0
    assert peak_non_reflect < 0.6 * peak_copy
