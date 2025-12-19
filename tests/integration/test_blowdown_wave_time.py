import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import muscl_hancock_step


@pytest.mark.integration
def test_blowdown_wave_time() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 1e-4
    cells = 50

    U = np.zeros((cells, 4))
    U[:, 0] = 1.2
    U[:, 1] = 0.0
    U[:, 2] = 1.2 * (R * 300.0 / (gamma - 1.0))
    U[:, 3] = 1.2

    U[0, 2] *= 2.0

    probe_idx = 25
    base_pressure = (gamma - 1.0) * (U[probe_idx, 2] - 0.5 * (U[probe_idx, 1] ** 2) / U[probe_idx, 0])

    arrival_step = None
    for step in range(500):
        U = muscl_hancock_step(U, dx, dt, gamma, R)
        pressure = (gamma - 1.0) * (U[probe_idx, 2] - 0.5 * (U[probe_idx, 1] ** 2) / U[probe_idx, 0])
        if pressure > 1.05 * base_pressure:
            arrival_step = step
            break

    assert arrival_step is not None
    time = arrival_step * dt
    assert 0.0 < time < 0.1
