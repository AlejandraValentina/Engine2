import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import muscl_hancock_step


def test_scalar_guard_runs_post_guard_only() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 0.0

    U = np.zeros((2, 4))
    U[:, 0] = [ -1e-6, 1.0 ]
    U[:, 1] = 0.0
    U[:, 2] = np.array([1.0, 1.0]) * (R * 300.0 / (gamma - 1.0))
    # set rhoY so that Y would be huge if checked before density fix
    U[:, 3] = np.array([5e-4, 0.8])

    U_new = muscl_hancock_step(U, dx, dt, gamma, R)
    assert np.isfinite(U_new).all()
