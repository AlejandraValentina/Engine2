import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import conserved_to_primitive, muscl_hancock_step


def test_solver1d_clamps_passive_scalar_Y() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 1e-4

    cells = 5
    rho = 1.2
    u = 0.0
    T = 300.0
    E = R * T / (gamma - 1.0)

    U = np.zeros((cells + 2, 4))
    U[1:-1, 0] = rho
    U[1:-1, 1] = rho * u
    U[1:-1, 2] = rho * (E + 0.5 * u * u)
    Y_init = np.array([-5e-4, 0.0, 0.5, 1.0, 1.0 + 5e-4])
    U[1:-1, 3] = rho * Y_init
    U[0] = U[1]
    U[-1] = U[-2]

    U_new = muscl_hancock_step(U, dx, dt, gamma, R)
    prim = conserved_to_primitive(U_new[1:-1], gamma, R)
    Y = prim[:, 4]

    assert np.isfinite(Y).all()
    assert Y.min() >= 0.0
    assert Y.max() <= 1.0
    assert np.allclose(U_new[1:-1, 3], prim[:, 0] * prim[:, 4])


def test_solver1d_passive_scalar_raises_on_large_drift() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 0.0

    U = np.zeros((4, 4))
    U[1:-1, 0] = 1.0
    U[1:-1, 1] = 0.0
    U[1:-1, 2] = 1.0 * (R * 300.0 / (gamma - 1.0))
    U[1:-1, 3] = np.array([-0.02, 1.05])
    U[0] = U[1]
    U[-1] = U[-2]

    with pytest.raises(ValueError):
        muscl_hancock_step(U, dx, dt, gamma, R)


def test_solver1d_passive_scalar_uses_rho_safe() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 0.0

    rho = 1e-12
    Y_init = 0.5
    rho_safe = max(rho, 1e-9)
    expected_Y = (rho * Y_init) / rho_safe
    expected_rhoY = rho_safe * expected_Y

    U = np.zeros((3, 4))
    U[1, 0] = rho
    U[1, 1] = 0.0
    U[1, 2] = rho * (R * 300.0 / (gamma - 1.0))
    U[1, 3] = rho * Y_init
    U[0] = U[1]
    U[-1] = U[1]

    U_new = muscl_hancock_step(U, dx, dt, gamma, R)
    assert np.allclose(U_new[1, 3], expected_rhoY)
