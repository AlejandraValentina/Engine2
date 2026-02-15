import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import muscl_hancock_step


def test_solver1d_reconstruction_rho_floor_stable() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 0.0

    cells = 6
    rho = np.full(cells, 1.2)
    rho[2] = -1e-12
    u = np.zeros(cells)
    T = 300.0
    E = R * T / (gamma - 1.0)

    U = np.zeros((cells, 4))
    U[:, 0] = rho
    U[:, 1] = rho * u
    U[:, 2] = rho * (E + 0.5 * u * u)
    U[:, 3] = np.maximum(rho, 1e-12) * 0.2

    U_new = muscl_hancock_step(U, dx, dt, gamma, R)

    assert np.isfinite(U_new).all()
    assert (U_new[:, 0] > 0.0).all()
