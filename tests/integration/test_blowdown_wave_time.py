import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import muscl_hancock_step


@pytest.mark.integration
@pytest.mark.slow
def test_blowdown_wave_time() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 1e-4
    cells = 50

    U = np.zeros((cells + 2, 4))
    U[1:-1, 0] = 1.2
    U[1:-1, 1] = 0.0
    U[1:-1, 2] = 1.2 * (R * 300.0 / (gamma - 1.0))
    U[1:-1, 3] = 1.2
    U[0] = U[1]
    U[-1] = U[-2]

    U[1, 2] *= 2.0

    probe_idx = 25
    probe_cell = 1 + probe_idx
    base_pressure = (gamma - 1.0) * (U[probe_cell, 2] - 0.5 * (U[probe_cell, 1] ** 2) / U[probe_cell, 0])

    arrival_step = None
    for step in range(500):
        U = muscl_hancock_step(U, dx, dt, gamma, R)
        pressure = (gamma - 1.0) * (U[probe_cell, 2] - 0.5 * (U[probe_cell, 1] ** 2) / U[probe_cell, 0])
        if pressure > 1.05 * base_pressure:
            arrival_step = step
            break

    assert arrival_step is not None
    time = arrival_step * dt
    assert 0.0 < time < 0.1
