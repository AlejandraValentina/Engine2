from __future__ import annotations

import numpy as np

from core.advanced.limiters import minmod


def conserved_to_primitive(U: np.ndarray, gamma: float, gas_constant: float) -> np.ndarray:
    rho = U[:, 0]
    u = U[:, 1] / rho
    E = U[:, 2] / rho
    e_int = E - 0.5 * u * u
    T = np.maximum(e_int * (gamma - 1.0) / gas_constant, 1e-9)
    p = rho * gas_constant * T
    Y = U[:, 3] / rho
    return np.stack([rho, u, p, T, Y], axis=1)


def flux(U: np.ndarray, gamma: float) -> np.ndarray:
    rho = U[:, 0]
    u = U[:, 1] / rho
    p = (gamma - 1.0) * (U[:, 2] - 0.5 * rho * u * u)
    F = np.zeros_like(U)
    F[:, 0] = rho * u
    F[:, 1] = rho * u * u + p
    F[:, 2] = u * (U[:, 2] + p)
    F[:, 3] = U[:, 3] * u
    return F


def muscl_hancock_step(
    U: np.ndarray,
    dx: float,
    dt: float,
    gamma: float,
    gas_constant: float,
    friction_factor: float = 0.0,
    diameter: float = 1.0,
) -> np.ndarray:
    """Advance one step with MUSCL-Hancock + Rusanov."""

    N = U.shape[0]
    U_ext = np.zeros((N + 2, 4))
    U_ext[1:-1] = U
    U_ext[0] = U[0]
    U_ext[-1] = U[-1]

    dU_plus = U_ext[2:] - U_ext[1:-1]
    dU_minus = U_ext[1:-1] - U_ext[:-2]
    slopes = minmod(dU_minus, dU_plus)

    U_L = U_ext[1:-1] + 0.5 * slopes
    U_R = U_ext[1:-1] - 0.5 * slopes

    F_L = flux(U_L, gamma)
    F_R = flux(U_R, gamma)
    U_half = 0.5 * (U_L + U_R) - 0.5 * dt / dx * (F_L - F_R)

    U_half_ext = np.zeros((N + 2, 4))
    U_half_ext[1:-1] = U_half
    U_half_ext[0] = U_half[0]
    U_half_ext[-1] = U_half[-1]

    UL = U_half_ext[:-1]
    UR = U_half_ext[1:]

    F_UL = flux(UL, gamma)
    F_UR = flux(UR, gamma)

    prim_L = conserved_to_primitive(UL, gamma, gas_constant)
    prim_R = conserved_to_primitive(UR, gamma, gas_constant)
    a_L = np.sqrt(gamma * prim_L[:, 2] / prim_L[:, 0])
    a_R = np.sqrt(gamma * prim_R[:, 2] / prim_R[:, 0])
    smax = np.maximum(np.abs(prim_L[:, 1]) + a_L, np.abs(prim_R[:, 1]) + a_R)

    F_star = 0.5 * (F_UL + F_UR) - 0.5 * smax[:, None] * (UR - UL)

    U_new = U - dt / dx * (F_star[1:] - F_star[:-1])

    if friction_factor > 0.0:
        rho = U_new[:, 0]
        u = U_new[:, 1] / rho
        S_mom = -(friction_factor / (2.0 * diameter)) * rho * u * np.abs(u)
        U_new[:, 1] += dt * S_mom
        U_new[:, 2] += dt * u * S_mom

    return U_new


def cfl_dt(U: np.ndarray, dx: float, gamma: float, gas_constant: float, cfl: float, dt_max: float) -> float:
    prim = conserved_to_primitive(U, gamma, gas_constant)
    a = np.sqrt(gamma * prim[:, 2] / prim[:, 0])
    max_speed = np.max(np.abs(prim[:, 1]) + a)
    return min(dt_max, cfl * dx / max(max_speed, 1e-9))
