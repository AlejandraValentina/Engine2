import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("numba")

import numpy as np

from core.advanced.solver_1d import muscl_hancock_step


def _build_state(n_phys: int, gamma: float, gas_constant: float) -> np.ndarray:
    x = np.linspace(0.0, 1.0, n_phys)
    rho = 1.15 + 0.04 * np.sin(2.0 * np.pi * x)
    u = 12.0 + 0.1 * np.cos(2.0 * np.pi * x)
    p = 101325.0 + 400.0 * np.sin(2.0 * np.pi * x)
    Y = 0.4 + 0.03 * np.cos(2.0 * np.pi * x)
    R = gas_constant
    E = R * 300.0 / (gamma - 1.0) + 0.5 * u * u
    U = np.zeros((n_phys + 2, 4))
    U[1:-1, 0] = rho
    U[1:-1, 1] = rho * u
    U[1:-1, 2] = rho * E
    U[1:-1, 3] = rho * Y
    U[0] = U[1]
    U[-1] = U[-2]
    return U


def test_solver1d_numba_matches_python_step() -> None:
    gamma = 1.35
    gas_constant = 287.0
    U = _build_state(8, gamma, gas_constant)
    dx = 0.1
    dt = 1e-5

    U_py = muscl_hancock_step(
        U.copy(),
        dx,
        dt,
        gamma,
        gas_constant,
        outlet_mode="copy",
        use_numba_1d=False,
    )
    U_nb = muscl_hancock_step(
        U.copy(),
        dx,
        dt,
        gamma,
        gas_constant,
        outlet_mode="copy",
        use_numba_1d=True,
    )
    diff = np.max(np.abs(U_py - U_nb))
    assert diff <= 1e-10
