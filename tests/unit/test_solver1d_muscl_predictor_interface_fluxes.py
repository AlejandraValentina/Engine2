import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import conserved_to_primitive, flux, muscl_hancock_step


def _first_order_rusanov(U: np.ndarray, dx: float, dt: float, gamma: float, gas_constant: float) -> np.ndarray:
    N = U.shape[0]
    U_ext = np.zeros((N + 2, 4))
    U_ext[1:-1] = U
    U_ext[0] = U[0]
    U_ext[-1] = U[-1]

    UL = U_ext[:-1]
    UR = U_ext[1:]

    F_UL = flux(UL, gamma)
    F_UR = flux(UR, gamma)

    prim_L = conserved_to_primitive(UL, gamma, gas_constant)
    prim_R = conserved_to_primitive(UR, gamma, gas_constant)
    rho_L = np.maximum(prim_L[:, 0], 1e-9)
    rho_R = np.maximum(prim_R[:, 0], 1e-9)
    a_L = np.sqrt(gamma * prim_L[:, 2] / rho_L)
    a_R = np.sqrt(gamma * prim_R[:, 2] / rho_R)
    smax = np.maximum(np.abs(prim_L[:, 1]) + a_L, np.abs(prim_R[:, 1]) + a_R)

    F_star = 0.5 * (F_UL + F_UR) - 0.5 * smax[:, None] * (UR - UL)
    return U - dt / dx * (F_star[1:] - F_star[:-1])


def test_solver1d_muscl_predictor_uses_interface_fluxes() -> None:
    gamma = 1.4
    R = 287.0
    cells = 64
    length = 1.0
    dx = length / cells

    x = np.linspace(0.0, length, cells, endpoint=False)
    rho0 = 1.2 + 0.02 * np.sin(2.0 * np.pi * x / length)
    u0 = 30.0
    T0 = 300.0
    p0 = rho0 * R * T0
    E0 = R * T0 / (gamma - 1.0)

    U = np.zeros((cells, 4))
    U[:, 0] = rho0
    U[:, 1] = rho0 * u0
    U[:, 2] = rho0 * (E0 + 0.5 * u0 * u0)
    U[:, 3] = rho0 * 0.2

    a0 = np.sqrt(gamma * R * T0)
    dt = 0.3 * dx / (abs(u0) + a0)

    U_first = _first_order_rusanov(U, dx, dt, gamma, R)
    U_muscl = muscl_hancock_step(U, dx, dt, gamma, R)

    diff_first = np.linalg.norm(U_first[:, 0] - rho0)
    diff_muscl = np.linalg.norm(U_muscl[:, 0] - rho0)

    assert diff_muscl <= diff_first * 0.98
