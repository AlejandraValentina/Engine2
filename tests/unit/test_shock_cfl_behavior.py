import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import (
    ShockCFLConfig,
    ShockCFLSubstepsConfig,
    cfl_dt,
    muscl_hancock_step,
    shock_cfl_plan,
)


def _build_state(p_values: np.ndarray, gamma: float, rho: float = 1.2, u: float = 0.0) -> np.ndarray:
    U = np.zeros((len(p_values) + 2, 4))
    for idx, p in enumerate(p_values, start=1):
        e_int = p / max(rho, 1e-12) / max(gamma - 1.0, 1e-9)
        E = e_int + 0.5 * u * u
        U[idx, 0] = rho
        U[idx, 1] = rho * u
        U[idx, 2] = rho * E
        U[idx, 3] = rho * 0.2
    U[0] = U[1]
    U[-1] = U[-2]
    return U


def test_shock_cfl_disabled_is_parity() -> None:
    gamma = 1.4
    gas_constant = 287.0
    dx = 0.1
    cfl = 0.5
    dt_max = 1.0

    U = _build_state(np.array([1.0e5, 1.0e5, 1.0e5, 1.0e5]), gamma)
    dt_base = cfl_dt(U, dx, gamma, gas_constant, cfl, dt_max, ghost_left=1, ghost_right=1)

    cfg = ShockCFLConfig(enabled=False)
    dt_step, n_sub = shock_cfl_plan(U, dt_base, gamma, gas_constant, cfg, ghost_left=1, ghost_right=1)

    assert dt_step == pytest.approx(dt_base)
    assert n_sub == 1


def test_shock_cfl_reduces_dt_on_pressure_jump() -> None:
    gamma = 1.4
    gas_constant = 287.0
    dx = 0.1
    cfl = 0.5
    dt_max = 1.0

    U = _build_state(np.array([1.0e5, 1.0e5, 1.0e6, 1.0e6]), gamma)
    dt_base = cfl_dt(U, dx, gamma, gas_constant, cfl, dt_max, ghost_left=1, ghost_right=1)

    cfg = ShockCFLConfig(
        enabled=True,
        k=8.0,
        min_factor=0.25,
        substeps=ShockCFLSubstepsConfig(enabled=False),
    )
    dt_step, n_sub = shock_cfl_plan(U, dt_base, gamma, gas_constant, cfg, ghost_left=1, ghost_right=1)

    assert dt_step < dt_base
    assert n_sub == 1


def test_shock_cfl_monotonic_with_jump_strength() -> None:
    gamma = 1.4
    gas_constant = 287.0
    dt_base = 1.0e-4

    cfg = ShockCFLConfig(
        enabled=True,
        k=4.0,
        min_factor=0.2,
        substeps=ShockCFLSubstepsConfig(enabled=False),
    )

    U_small = _build_state(np.array([1.0e5, 1.05e5, 1.1e5, 1.1e5]), gamma)
    U_big = _build_state(np.array([1.0e5, 1.0e5, 1.0e6, 1.0e6]), gamma)

    dt_small, _ = shock_cfl_plan(U_small, dt_base, gamma, gas_constant, cfg, ghost_left=1, ghost_right=1)
    dt_big, _ = shock_cfl_plan(U_big, dt_base, gamma, gas_constant, cfg, ghost_left=1, ghost_right=1)

    assert dt_big < dt_small


def test_shock_cfl_substeps_keep_state_finite() -> None:
    gamma = 1.4
    gas_constant = 287.0
    dx = 0.1

    U = _build_state(np.array([1.0e5, 1.0e5, 1.0e6, 1.0e6]), gamma)
    cfg = ShockCFLConfig(
        enabled=True,
        k=6.0,
        min_factor=0.2,
        substeps=ShockCFLSubstepsConfig(enabled=True, max_substeps=4),
    )

    dt_base = 1.0e-4
    dt_step, n_sub = shock_cfl_plan(U, dt_base, gamma, gas_constant, cfg, ghost_left=1, ghost_right=1)
    assert n_sub > 1

    dt_sub = dt_step / n_sub
    U_sub = U.copy()
    for _ in range(n_sub):
        U_sub = muscl_hancock_step(U_sub, dx, dt_sub, gamma, gas_constant)

    assert np.isfinite(U_sub).all()


def test_shock_cfl_ignores_ghost_cells() -> None:
    gamma = 1.4
    gas_constant = 287.0
    dt_base = 1.0e-4

    cfg = ShockCFLConfig(
        enabled=True,
        k=6.0,
        min_factor=0.2,
        substeps=ShockCFLSubstepsConfig(enabled=False),
    )

    U = _build_state(np.array([1.0e5, 1.0e5, 1.0e6, 1.0e6]), gamma)
    dt_clean, _ = shock_cfl_plan(U, dt_base, gamma, gas_constant, cfg, ghost_left=1, ghost_right=1)

    U[0, 2] = 1.0e12
    U[-1, 2] = 1.0e12
    dt_ghost, _ = shock_cfl_plan(U, dt_base, gamma, gas_constant, cfg, ghost_left=1, ghost_right=1)

    assert dt_ghost == pytest.approx(dt_clean)
