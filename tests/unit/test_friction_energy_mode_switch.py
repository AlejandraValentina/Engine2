import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import muscl_hancock_step


def test_friction_energy_mode_switch() -> None:
    gamma = 1.4
    R = 287.0
    dx = 0.1
    dt = 1e-4

    cells = 3
    rho = 1.2
    u = 50.0
    T = 300.0
    E = R * T / (gamma - 1.0)

    U = np.zeros((cells + 2, 4))
    U[1:-1, 0] = rho
    U[1:-1, 1] = rho * u
    U[1:-1, 2] = rho * (E + 0.5 * u * u)
    U[1:-1, 3] = rho * 0.5
    U[0] = U[1]
    U[-1] = U[-2]

    U_adiabatic = muscl_hancock_step(
        U.copy(),
        dx,
        dt,
        gamma,
        R,
        friction_factor=0.1,
        friction_energy_mode="adiabatic",
    )
    U_wall = muscl_hancock_step(
        U.copy(),
        dx,
        dt,
        gamma,
        R,
        friction_factor=0.1,
        friction_energy_mode="wall_loss",
    )

    assert np.isfinite(U_adiabatic).all()
    assert np.isfinite(U_wall).all()
    assert U_wall[1:-1, 2].mean() < U_adiabatic[1:-1, 2].mean()
