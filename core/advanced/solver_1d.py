from __future__ import annotations

import logging
import numpy as np

logger = logging.getLogger(__name__)
_PRESSURE_FIX_COUNT = 0
_PRESSURE_FIX_LIMIT = 20
_PRESSURE_FLOOR = 1e-6
_DENSITY_FIX_COUNT = 0
_DENSITY_FIX_LIMIT = 20
_DENSITY_FLOOR = 1e-9
_VELOCITY_FIX_COUNT = 0
_VELOCITY_FIX_LIMIT = 20
_U_MAX = 5.0 * np.sqrt(1.35 * _PRESSURE_FLOOR / _DENSITY_FLOOR)


def reset_guard_counters() -> None:
    global _PRESSURE_FIX_COUNT, _DENSITY_FIX_COUNT, _VELOCITY_FIX_COUNT
    _PRESSURE_FIX_COUNT = 0
    _DENSITY_FIX_COUNT = 0
    _VELOCITY_FIX_COUNT = 0


def _guard_state(U: np.ndarray, gamma: float, gas_constant: float, label: str) -> None:
    global _DENSITY_FIX_COUNT, _PRESSURE_FIX_COUNT, _VELOCITY_FIX_COUNT
    if not np.isfinite(U).all():
        raise ValueError(f"Non-finite state in {label}")

    rho = U[:, 0]
    bad_rho = rho <= 0.0
    if np.any(bad_rho):
        _DENSITY_FIX_COUNT += int(np.count_nonzero(bad_rho))
        logger.error(
            "Density floor applied in %s: cells=%s min_rho=%.3e count=%d",
            label,
            np.where(bad_rho)[0].tolist(),
            float(np.min(rho)),
            _DENSITY_FIX_COUNT,
        )
        if _DENSITY_FIX_COUNT > _DENSITY_FIX_LIMIT:
            raise ValueError(f"Density floor limit exceeded in {label}")
        for idx in np.where(bad_rho)[0]:
            rho_old = float(U[idx, 0])
            mom_old = float(U[idx, 1])
            rho_safe = max(abs(rho_old), _DENSITY_FLOOR)
            u = mom_old / rho_safe
            if abs(u) > _U_MAX:
                _VELOCITY_FIX_COUNT += 1
                logger.error(
                    "Velocity cap applied in %s (density fix): cell=%d u=%.3e cap=%.3e count=%d",
                    label,
                    int(idx),
                    float(u),
                    float(_U_MAX),
                    _VELOCITY_FIX_COUNT,
                )
                if _VELOCITY_FIX_COUNT > _VELOCITY_FIX_LIMIT:
                    raise ValueError(f"Velocity cap limit exceeded in {label}")
                u = float(np.clip(u, -_U_MAX, _U_MAX))
            rho_fix = _DENSITY_FLOOR
            U[idx, 0] = rho_fix
            U[idx, 1] = rho_fix * u
            U[idx, 2] = _PRESSURE_FLOOR / (gamma - 1.0) + 0.5 * rho_fix * u * u

    rho_safe = np.maximum(U[:, 0], _DENSITY_FLOOR)
    u = U[:, 1] / rho_safe
    p = (gamma - 1.0) * (U[:, 2] - 0.5 * rho_safe * u * u)
    bad_p = (p <= 0.0) | (~np.isfinite(p))
    if np.any(bad_p):
        _PRESSURE_FIX_COUNT += int(np.count_nonzero(bad_p))
        logger.error(
            "Pressure floor applied in %s: cells=%s min_p=%.3e count=%d",
            label,
            np.where(bad_p)[0].tolist(),
            float(np.min(p)),
            _PRESSURE_FIX_COUNT,
        )
        if _PRESSURE_FIX_COUNT > _PRESSURE_FIX_LIMIT:
            raise ValueError(f"Pressure floor limit exceeded in {label}")
        for idx in np.where(bad_p)[0]:
            rho = float(U[idx, 0])
            u = float(U[idx, 1]) / max(rho, _DENSITY_FLOOR)
            if abs(u) > _U_MAX:
                _VELOCITY_FIX_COUNT += 1
                logger.error(
                    "Velocity cap applied in %s (pressure fix): cell=%d u=%.3e cap=%.3e count=%d",
                    label,
                    int(idx),
                    float(u),
                    float(_U_MAX),
                    _VELOCITY_FIX_COUNT,
                )
                if _VELOCITY_FIX_COUNT > _VELOCITY_FIX_LIMIT:
                    raise ValueError(f"Velocity cap limit exceeded in {label}")
                u = float(np.clip(u, -_U_MAX, _U_MAX))
            U[idx, 2] = _PRESSURE_FLOOR / (gamma - 1.0) + 0.5 * rho * u * u


def _pressure_from_conserved(U: np.ndarray, gamma: float) -> np.ndarray:
    rho = U[:, 0]
    rho_safe = np.maximum(rho, 1e-12)
    u = U[:, 1] / rho_safe
    return (gamma - 1.0) * (U[:, 2] - 0.5 * rho_safe * u * u)


def conserved_to_primitive(U: np.ndarray, gamma: float, gas_constant: float) -> np.ndarray:
    rho = U[:, 0]
    rho_safe = np.maximum(rho, 1e-12)
    u = U[:, 1] / rho_safe
    E = U[:, 2] / rho_safe
    e_int = E - 0.5 * u * u
    T = np.maximum(e_int * (gamma - 1.0) / gas_constant, 1e-9)
    p = rho_safe * gas_constant * T
    Y = U[:, 3] / rho_safe
    return np.stack([rho, u, p, T, Y], axis=1)


def flux(U: np.ndarray, gamma: float) -> np.ndarray:
    rho = U[:, 0]
    rho_safe = np.maximum(rho, 1e-12)
    u = U[:, 1] / rho_safe
    p = (gamma - 1.0) * (U[:, 2] - 0.5 * rho_safe * u * u)
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
    _guard_state(U, gamma, gas_constant, "muscl_hancock_step input")
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
    a_L = np.sqrt(gamma * prim_L[:, 2] / prim_L[:, 0])
    a_R = np.sqrt(gamma * prim_R[:, 2] / prim_R[:, 0])
    smax = np.maximum(np.abs(prim_L[:, 1]) + a_L, np.abs(prim_R[:, 1]) + a_R)

    F_star = 0.5 * (F_UL + F_UR) - 0.5 * smax[:, None] * (UR - UL)

    U_new = U - dt / dx * (F_star[1:] - F_star[:-1])

    if friction_factor > 0.0:
        rho = U_new[:, 0]
        rho_safe = np.maximum(rho, 1e-12)
        u = U_new[:, 1] / rho_safe
        S_mom = -(friction_factor / (2.0 * diameter)) * rho * u * np.abs(u)
        U_new[:, 1] += dt * S_mom
        U_new[:, 2] += dt * u * S_mom

    _guard_state(U_new, gamma, gas_constant, "muscl_hancock_step output")
    return U_new


def cfl_dt(U: np.ndarray, dx: float, gamma: float, gas_constant: float, cfl: float, dt_max: float) -> float:
    _guard_state(U, gamma, gas_constant, "cfl_dt input")
    prim = conserved_to_primitive(U, gamma, gas_constant)
    a = np.sqrt(gamma * prim[:, 2] / prim[:, 0])
    max_speed = np.max(np.abs(prim[:, 1]) + a)
    return min(dt_max, cfl * dx / max(max_speed, 1e-9))
