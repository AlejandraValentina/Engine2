import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import cfl_dt


def test_cfl_has_no_side_effects_on_U() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    cfl = 0.5
    dt_max = 1.0

    U = np.zeros((4, 4))
    # ghost cell (index 0)
    U[0, 0] = 1.0
    U[0, 1] = 5.0e5
    U[0, 2] = 1.0e6
    U[0, 3] = 0.5
    # physical cells
    rho = 1.2
    u = 20.0
    T = 300.0
    E = R * T / (gamma - 1.0)
    for i in (1, 2):
        U[i, 0] = rho
        U[i, 1] = rho * u
        U[i, 2] = rho * (E + 0.5 * u * u)
        U[i, 3] = rho * 0.2
    U[-1] = U[2]

    U_before = U.copy()
    _ = cfl_dt(U, dx, gamma, R, cfl, dt_max, ghost_left=1, ghost_right=1)

    assert np.array_equal(U, U_before)
