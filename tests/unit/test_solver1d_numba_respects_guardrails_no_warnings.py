import warnings

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("numba")

import numpy as np

from core.advanced.solver_1d import muscl_hancock_step


def test_solver1d_numba_respects_guardrails_no_warnings() -> None:
    gamma = 1.35
    gas_constant = 287.0
    n_phys = 6
    rho = 1.2
    u = 5.0
    p = 101325.0
    E = gas_constant * 300.0 / (gamma - 1.0) + 0.5 * u * u
    U = np.zeros((n_phys + 2, 4))
    U[1:-1, 0] = rho
    U[1:-1, 1] = rho * u
    U[1:-1, 2] = rho * E
    U[1:-1, 3] = rho * 0.5
    U[0] = U[1]
    U[-1] = U[-2]

    dx = 0.1
    dt = 1e-5

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        for _ in range(3):
            U = muscl_hancock_step(
                U,
                dx,
                dt,
                gamma,
                gas_constant,
                outlet_mode="copy",
                use_numba_1d=True,
            )
    assert np.isfinite(U).all()
