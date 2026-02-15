import pytest

np = pytest.importorskip("numpy")

from core.advanced.solver_1d import cfl_dt


def test_cfl_dt_decreases_with_speed() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    cfl = 0.5
    dt_max = 1.0

    U = np.zeros((5, 4))
    U[:, 0] = 1.2
    U[:, 1] = 0.0
    U[:, 2] = 1.2 * (R * 300.0 / (gamma - 1.0))
    U[:, 3] = 1.2

    dt0 = cfl_dt(U, dx, gamma, R, cfl, dt_max)
    U[:, 1] = 1.2 * 50.0
    dt1 = cfl_dt(U, dx, gamma, R, cfl, dt_max)

    assert dt1 < dt0
