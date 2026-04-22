import pytest

np = pytest.importorskip("numpy")

from core.advanced.solver_1d import muscl_hancock_step


def test_passive_scalar_bounds() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 1e-4

    cells = 10
    U = np.zeros((cells + 2, 4))
    U[1:-1, 0] = 1.0
    U[1:-1, 1] = 1.0
    U[1:-1, 2] = 1.0 * (R * 300.0 / (gamma - 1.0))
    U[1:-1, 3] = 0.5
    U[0] = U[1]
    U[-1] = U[-2]

    U_new = muscl_hancock_step(U, dx, dt, gamma, R)
    Y = U_new[1:-1, 3] / U_new[1:-1, 0]
    assert np.isfinite(Y).all()
    assert Y.min() >= -1e-6
    assert Y.max() <= 1.0 + 1e-6
