import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced import solver_1d
from core.advanced.solver_1d import muscl_hancock_step


def _build_state(n_phys: int, gamma: float, gas_constant: float) -> np.ndarray:
    x = np.linspace(0.0, 1.0, n_phys)
    rho = 1.1 + 0.02 * np.sin(2.0 * np.pi * x)
    u = 8.0 + 0.1 * np.cos(2.0 * np.pi * x)
    p = 101325.0 + 200.0 * np.sin(2.0 * np.pi * x)
    Y = 0.3 + 0.02 * np.cos(2.0 * np.pi * x)
    E = gas_constant * 300.0 / (gamma - 1.0) + 0.5 * u * u
    U = np.zeros((n_phys + 2, 4))
    U[1:-1, 0] = rho
    U[1:-1, 1] = rho * u
    U[1:-1, 2] = rho * E
    U[1:-1, 3] = rho * Y
    U[0] = U[1]
    U[-1] = U[-2]
    return U


def test_numba_disabled_still_runs_python_path(monkeypatch: pytest.MonkeyPatch) -> None:
    gamma = 1.35
    gas_constant = 287.0
    U = _build_state(6, gamma, gas_constant)
    dx = 0.1
    dt = 2e-5

    U_py = muscl_hancock_step(U.copy(), dx, dt, gamma, gas_constant, use_numba_1d=False)

    monkeypatch.setattr(solver_1d, "_HAS_NUMBA", False)
    U_nb = muscl_hancock_step(U.copy(), dx, dt, gamma, gas_constant, use_numba_1d=True)

    assert np.allclose(U_py, U_nb)


def test_numba_parity_one_step() -> None:
    pytest.importorskip("numba")
    if not solver_1d._HAS_NUMBA:
        pytest.skip("numba not available")

    gamma = 1.35
    gas_constant = 287.0
    U = _build_state(6, gamma, gas_constant)
    dx = 0.1
    dt = 2e-5

    U_py = muscl_hancock_step(U.copy(), dx, dt, gamma, gas_constant, use_numba_1d=False)
    U_nb = muscl_hancock_step(U.copy(), dx, dt, gamma, gas_constant, use_numba_1d=True)

    assert np.max(np.abs(U_py - U_nb)) <= 1e-10
