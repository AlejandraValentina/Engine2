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


def test_solver1d_numba_matches_python_step_with_losses_and_outlet() -> None:
    gamma = 1.35
    gas_constant = 287.0
    n_phys = 10
    x = np.linspace(0.0, 1.0, n_phys)
    area = 0.8 + 0.4 * x  # tapered profile to emulate dA/dx effects in initial state
    rho = 1.2 + 0.02 * np.sin(2.0 * np.pi * x)
    mdot = 0.8
    u = mdot / np.maximum(rho * area, 1e-9)
    p = 101325.0 + 300.0 * np.cos(2.0 * np.pi * x)
    Y = np.where(x < 0.5, 0.1, 0.9)
    E = gas_constant * 320.0 / (gamma - 1.0) + 0.5 * u * u
    U = np.zeros((n_phys + 2, 4))
    U[1:-1, 0] = rho
    U[1:-1, 1] = rho * u
    U[1:-1, 2] = rho * E
    U[1:-1, 3] = rho * Y
    U[0] = U[1]
    U[-1] = U[-2]

    dx = 0.08
    dt = 5e-6
    friction_factor = 0.02

    U_py = muscl_hancock_step(
        U.copy(),
        dx,
        dt,
        gamma,
        gas_constant,
        friction_factor=friction_factor,
        outlet_mode="copy",
        use_numba_1d=False,
    )
    U_nb = muscl_hancock_step(
        U.copy(),
        dx,
        dt,
        gamma,
        gas_constant,
        friction_factor=friction_factor,
        outlet_mode="copy",
        use_numba_1d=True,
    )
    diff = np.max(np.abs(U_py - U_nb))
    assert diff <= 1e-10

    p_outlet = 100000.0
    U_py_out = muscl_hancock_step(
        U.copy(),
        dx,
        dt,
        gamma,
        gas_constant,
        p_outlet=p_outlet,
        outlet_mode="non_reflecting",
        use_numba_1d=False,
    )
    U_nb_out = muscl_hancock_step(
        U.copy(),
        dx,
        dt,
        gamma,
        gas_constant,
        p_outlet=p_outlet,
        outlet_mode="non_reflecting",
        use_numba_1d=True,
    )
    diff_out = np.max(np.abs(U_py_out - U_nb_out))
    assert diff_out <= 1e-10


def test_solver1d_numba_matches_python_multistep_with_outlet() -> None:
    gamma = 1.35
    gas_constant = 287.0
    U_py = _build_state(12, gamma, gas_constant)
    U_nb = U_py.copy()
    dx = 0.1
    dt = 1e-5

    for _ in range(25):
        U_py = muscl_hancock_step(
            U_py,
            dx,
            dt,
            gamma,
            gas_constant,
            p_outlet=100000.0,
            outlet_mode="non_reflecting",
            use_numba_1d=False,
        )
        U_nb = muscl_hancock_step(
            U_nb,
            dx,
            dt,
            gamma,
            gas_constant,
            p_outlet=100000.0,
            outlet_mode="non_reflecting",
            use_numba_1d=True,
        )

    diff = np.max(np.abs(U_py - U_nb))
    assert diff <= 1e-10


def test_solver1d_numba_matches_python_multistep_with_guardrail_like_state() -> None:
    gamma = 1.35
    gas_constant = 287.0
    n_phys = 12
    x = np.linspace(0.0, 1.0, n_phys)
    rho = 0.12 + 0.08 * np.where(x < 0.5, 1.0, 0.5) + 0.02 * np.sin(2.0 * np.pi * x)
    u = np.where(x < 0.5, 45.0, -35.0)
    p = np.where(x < 0.5, 160000.0, 85000.0) + 2500.0 * np.sin(2.0 * np.pi * x)
    Y = np.clip(0.15 + 0.7 * x, 0.0, 1.0)
    E = p / np.maximum(rho, 1e-9) / (gamma - 1.0) + 0.5 * u * u

    U_py = np.zeros((n_phys + 2, 4))
    U_py[1:-1, 0] = rho
    U_py[1:-1, 1] = rho * u
    U_py[1:-1, 2] = rho * E
    U_py[1:-1, 3] = rho * Y
    U_py[0] = U_py[1]
    U_py[-1] = U_py[-2]
    U_nb = U_py.copy()

    for _ in range(80):
        U_py = muscl_hancock_step(
            U_py,
            0.08,
            3e-6,
            gamma,
            gas_constant,
            friction_factor=0.03,
            p_outlet=90000.0,
            outlet_mode="non_reflecting",
            use_numba_1d=False,
        )
        U_nb = muscl_hancock_step(
            U_nb,
            0.08,
            3e-6,
            gamma,
            gas_constant,
            friction_factor=0.03,
            p_outlet=90000.0,
            outlet_mode="non_reflecting",
            use_numba_1d=True,
        )

    assert np.isfinite(U_py).all()
    assert np.isfinite(U_nb).all()
    assert float(np.min(U_py[1:-1, 0])) > 0.1
    diff = np.max(np.abs(U_py - U_nb))
    assert diff <= 1e-10
