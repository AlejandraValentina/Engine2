import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import cfl_dt


def test_cfl_ignores_ghost_left_extremes() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    cfl = 0.5
    dt_max = 1e-3

    U = np.zeros((4, 4))
    # ghost cell (index 0)
    U[0, 0] = 1.0
    U[0, 1] = 1.0e6
    U[0, 2] = 1.0e6
    U[0, 3] = 0.5
    # physical cells
    rho = 1.2
    u = 10.0
    T = 300.0
    E = R * T / (gamma - 1.0)
    for i in (1, 2):
        U[i, 0] = rho
        U[i, 1] = rho * u
        U[i, 2] = rho * (E + 0.5 * u * u)
        U[i, 3] = rho * 0.2
    U[-1] = U[2]

    dt0 = cfl_dt(U, dx, gamma, R, cfl, dt_max, ghost_left=1, ghost_right=1)
    U[0, 1] = 2.0e6
    U[0, 2] = 2.0e6
    dt1 = cfl_dt(U, dx, gamma, R, cfl, dt_max, ghost_left=1, ghost_right=1)

    assert dt0 == pytest.approx(dt1, rel=1e-9, abs=1e-12)
