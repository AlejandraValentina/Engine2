import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import conserved_to_primitive, muscl_hancock_step


def test_solver1d_rhoY_consistent_after_density_floor() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 0.0

    U = np.zeros((4, 4))
    U[1:-1, 0] = [ -1e-6, 1.0 ]
    U[1:-1, 1] = 0.0
    U[1:-1, 2] = np.array([1.0, 1.0]) * (R * 300.0 / (gamma - 1.0))
    U[1:-1, 3] = np.array([0.2, 0.8])
    U[0] = U[1]
    U[-1] = U[-2]

    U_new = muscl_hancock_step(U, dx, dt, gamma, R)
    prim = conserved_to_primitive(U_new[1:-1], gamma, R)
    Y = prim[:, 4]

    assert np.isfinite(Y).all()
    assert Y.min() >= 0.0
    assert Y.max() <= 1.0
    assert np.allclose(U_new[1:-1, 3], prim[:, 0] * prim[:, 4])
