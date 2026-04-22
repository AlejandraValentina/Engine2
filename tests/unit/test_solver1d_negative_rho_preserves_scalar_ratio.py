import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import muscl_hancock_step


def test_solver1d_negative_rho_preserves_scalar_ratio() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 0.0

    U = np.zeros((4, 4))
    U[1, 0] = -1e-6
    U[1, 1] = 0.0
    U[1, 2] = 1.0
    U[1, 3] = 5e-7

    U[2, 0] = 1.0
    U[2, 1] = 0.0
    U[2, 2] = U[2, 0] * (R * 300.0 / (gamma - 1.0))
    U[2, 3] = 0.5
    U[0] = U[1]
    U[-1] = U[2]

    U_new = muscl_hancock_step(U, dx, dt, gamma, R)

    rho = U_new[1, 0]
    Y = U_new[1, 3] / rho

    assert rho > 0.0
    assert np.isfinite(Y)
    assert Y == pytest.approx(0.5, rel=1e-6, abs=1e-6)
