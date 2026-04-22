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

    U0 = np.zeros((cells + 2, 4))
    U0[1:-1, 0] = rho0
    U0[1:-1, 1] = rho0 * u0
    U0[1:-1, 2] = rho0 * (E0 + 0.5 * u0 * u0)
    U0[1:-1, 3] = rho0 * 0.2
    U0[0] = U0[1]
    U0[-1] = U0[-2]

    U0[3, 2] *= 1.2

    a0 = np.sqrt(gamma * R * T0)
    dt = 0.4 * dx / a0
    steps = int(2.0 * length / (a0 * dt))

    def run_case(p_outlet: float | None) -> tuple[float, float]:
        U = U0.copy()
        peak = 0.0
        tail_pressures = []
        t_start = length / a0
        for step in range(steps):
            U = muscl_hancock_step(U, dx, dt, gamma, R, p_outlet=p_outlet)
            if step * dt < t_start:
                continue
            p_probe = _pressure_from_state(U[1:-1], gamma)[-3]
            peak = max(peak, p_probe - p0)
            if step > int(0.7 * steps):
                tail_pressures.append(p_probe)
        mean_tail = float(np.mean(tail_pressures)) if tail_pressures else float(p_probe)
        return peak, mean_tail

    peak_copy, _ = run_case(None)
    peak_non_reflect, mean_p1 = run_case(0.9 * p0)
    _, mean_p2 = run_case(1.1 * p0)

    assert peak_copy > 0.0
    assert peak_non_reflect < 0.6 * peak_copy
    assert mean_p2 > mean_p1
    assert abs(mean_p1 - 0.9 * p0) < 0.3 * p0
    assert abs(mean_p2 - 1.1 * p0) < 0.3 * p0
