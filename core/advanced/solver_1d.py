from __future__ import annotations

import logging
import math
import numpy as np

from core.advanced.limiters import minmod

logger = logging.getLogger(__name__)
_PRESSURE_FIX_COUNT = 0
_PRESSURE_FIX_LIMIT = 20
_PRESSURE_FLOOR = 1e-6
_DENSITY_FIX_COUNT = 0
_DENSITY_FIX_LIMIT = 20
_DENSITY_FLOOR = 1e-9
_VELOCITY_FIX_COUNT = 0
_VELOCITY_FIX_LIMIT = 20
_OUTLET_FALLBACK_COUNT = 0
_OUTLET_FALLBACK_LIMIT = 10

def _u_max(gamma: float) -> float:
    return 200.0 * math.sqrt(max(gamma, 1e-9))


def reset_guard_counters() -> None:
    global _PRESSURE_FIX_COUNT, _DENSITY_FIX_COUNT, _VELOCITY_FIX_COUNT, _OUTLET_FALLBACK_COUNT
    _PRESSURE_FIX_COUNT = 0
    _DENSITY_FIX_COUNT = 0
    _VELOCITY_FIX_COUNT = 0
    _OUTLET_FALLBACK_COUNT = 0


def _guard_state(U: np.ndarray, gamma: float, gas_constant: float, label: str) -> None:
    global _DENSITY_FIX_COUNT, _PRESSURE_FIX_COUNT, _VELOCITY_FIX_COUNT
    if not np.isfinite(U).all():
        raise ValueError(f"Non-finite state in {label}")

    u_cap = _u_max(gamma)
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
            rhoY_old = float(U[idx, 3])
            rho_safe = max(abs(rho_old), _DENSITY_FLOOR)
            u = mom_old / rho_safe
            if abs(u) > u_cap:
                _VELOCITY_FIX_COUNT += 1
                logger.error(
                    "Velocity cap applied in %s (density fix): cell=%d u=%.3e cap=%.3e count=%d",
                    label,
                    int(idx),
                    float(u),
                    float(u_cap),
                    _VELOCITY_FIX_COUNT,
                )
                if _VELOCITY_FIX_COUNT > _VELOCITY_FIX_LIMIT:
                    raise ValueError(f"Velocity cap limit exceeded in {label}")
                u = float(np.clip(u, -u_cap, u_cap))
            Y_old = rhoY_old / max(rho_old, _DENSITY_FLOOR)
            Y_old = float(np.clip(Y_old, 0.0, 1.0))
            rho_fix = _DENSITY_FLOOR
            U[idx, 0] = rho_fix
            U[idx, 1] = rho_fix * u
            U[idx, 2] = _PRESSURE_FLOOR / (gamma - 1.0) + 0.5 * rho_fix * u * u
            U[idx, 3] = rho_fix * Y_old

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
            rhoY_old = float(U[idx, 3])
            u = float(U[idx, 1]) / max(rho, _DENSITY_FLOOR)
            if abs(u) > u_cap:
                _VELOCITY_FIX_COUNT += 1
                logger.error(
                    "Velocity cap applied in %s (pressure fix): cell=%d u=%.3e cap=%.3e count=%d",
                    label,
                    int(idx),
                    float(u),
                    float(u_cap),
                    _VELOCITY_FIX_COUNT,
                )
                if _VELOCITY_FIX_COUNT > _VELOCITY_FIX_LIMIT:
                    raise ValueError(f"Velocity cap limit exceeded in {label}")
                u = float(np.clip(u, -u_cap, u_cap))
            U[idx, 2] = _PRESSURE_FLOOR / (gamma - 1.0) + 0.5 * rho * u * u
            Y_old = rhoY_old / max(rho, _DENSITY_FLOOR)
            Y_old = float(np.clip(Y_old, 0.0, 1.0))
            rho_fix = rho if rho > 0.0 else _DENSITY_FLOOR
            U[idx, 3] = rho_fix * Y_old


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


def _primitive_to_conserved(prim: np.ndarray, gamma: float, gas_constant: float, label: str) -> np.ndarray:
    global _DENSITY_FIX_COUNT, _PRESSURE_FIX_COUNT
    rho = prim[:, 0]
    u = prim[:, 1]
    p = prim[:, 2]
    Y = prim[:, 3]

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
        rho = np.where(bad_rho, _DENSITY_FLOOR, rho)

    bad_p = p <= 0.0
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
        p = np.where(bad_p, _PRESSURE_FLOOR, p)

    T = p / (rho * gas_constant)
    e_int = gas_constant * T / (gamma - 1.0)
    E = e_int + 0.5 * u * u
    U = np.zeros((prim.shape[0], 4))
    U[:, 0] = rho
    U[:, 1] = rho * u
    U[:, 2] = rho * E
    U[:, 3] = rho * Y
    return U


def _primitive_to_conserved_row(prim4: np.ndarray, gamma: float, gas_constant: float) -> np.ndarray:
    rho = float(prim4[0])
    u = float(prim4[1])
    p = float(prim4[2])
    Y = float(prim4[3])
    if rho <= 0.0:
        raise ValueError("rho must be positive")
    if p <= 0.0:
        raise ValueError("p must be positive")
    T = p / (rho * gas_constant)
    e_int = gas_constant * T / (gamma - 1.0)
    E = e_int + 0.5 * u * u
    return np.array([rho, rho * u, rho * E, rho * Y], dtype=float)


def _friction_factor_swamee_jain(
    Re: np.ndarray, roughness: float, diameter: float
) -> np.ndarray:
    if diameter <= 0.0:
        raise ValueError("diameter must be positive")
    if roughness < 0.0:
        raise ValueError("roughness must be non-negative")
    Re_safe = np.maximum(Re, 1e-8)
    rel_eps = roughness / diameter
    f_lam = 64.0 / Re_safe
    term = rel_eps / 3.7 + 5.74 / np.power(Re_safe, 0.9)
    f_turb = 0.25 / np.square(np.log10(term))
    return np.where(Re_safe < 2300.0, f_lam, f_turb)


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


def _rusanov_flux(UL: np.ndarray, UR: np.ndarray, gamma: float, gas_constant: float) -> np.ndarray:
    F_UL = flux(UL, gamma)
    F_UR = flux(UR, gamma)

    prim_L = conserved_to_primitive(UL, gamma, gas_constant)
    prim_R = conserved_to_primitive(UR, gamma, gas_constant)
    a_L = np.sqrt(gamma * prim_L[:, 2] / np.maximum(prim_L[:, 0], _DENSITY_FLOOR))
    a_R = np.sqrt(gamma * prim_R[:, 2] / np.maximum(prim_R[:, 0], _DENSITY_FLOOR))
    smax = np.maximum(np.abs(prim_L[:, 1]) + a_L, np.abs(prim_R[:, 1]) + a_R)

    return 0.5 * (F_UL + F_UR) - 0.5 * smax[:, None] * (UR - UL)


def _apply_scalar_guard(U: np.ndarray, label: str) -> None:
    rho = U[:, 0]
    rho_safe = np.maximum(rho, _DENSITY_FLOOR)
    Y = U[:, 3] / rho_safe
    Y_clipped = np.clip(Y, 0.0, 1.0)
    max_delta = float(np.max(np.abs(Y - Y_clipped)))
    if max_delta > 1e-3:
        bad_idx = np.where(np.abs(Y - Y_clipped) > 1e-3)[0].tolist()
        raise ValueError(
            "Passive scalar out of bounds in "
            f"{label}: min={float(np.min(Y)):.3e} max={float(np.max(Y)):.3e} idx={bad_idx}"
        )
    U[:, 3] = rho_safe * Y_clipped


def _outlet_primitive(prim_i: np.ndarray, p_outlet: float, gamma: float) -> np.ndarray:
    rho_i = float(prim_i[0])
    u_i = float(prim_i[1])
    p_i = float(prim_i[2])
    Y_i = float(prim_i[3])

    rho_safe = max(rho_i, _DENSITY_FLOOR)
    p_safe = max(p_i, _PRESSURE_FLOOR)
    a_i = math.sqrt(gamma * p_safe / rho_safe)

    if u_i <= 0.0 or abs(u_i) >= a_i:
        return np.array([rho_i, u_i, p_i, Y_i], dtype=float)

    p_out = max(p_outlet, _PRESSURE_FLOOR)
    rho_out = rho_safe * (p_out / p_safe) ** (1.0 / gamma)
    a_out = math.sqrt(gamma * p_out / rho_out)
    J_plus = u_i + 2.0 * a_i / (gamma - 1.0)
    u_out = J_plus - 2.0 * a_out / (gamma - 1.0)

    if not math.isfinite(u_out) or u_out <= 0.0:
        return np.array([rho_i, u_i, p_i, Y_i], dtype=float)

    return np.array([rho_out, u_out, p_out, Y_i], dtype=float)


def _outlet_primitive_bc(
    prim_i: np.ndarray,
    p_outlet: float,
    gamma: float,
    gas_constant: float,
    outlet_mode: str,
    reflection_coeff: float | None,
    impedance: float | None,
) -> np.ndarray:
    global _OUTLET_FALLBACK_COUNT
    if outlet_mode == "copy":
        return prim_i
    if outlet_mode == "non_reflecting":
        return _outlet_primitive(prim_i, p_outlet, gamma)
    if outlet_mode != "impedance":
        raise ValueError(f"Unknown outlet_mode '{outlet_mode}'")

    rho_i = float(prim_i[0])
    u_i = float(prim_i[1])
    p_i = float(prim_i[2])
    Y_i = float(prim_i[3])
    rho_safe = max(rho_i, _DENSITY_FLOOR)
    p_safe = max(p_i, _PRESSURE_FLOOR)
    a_i = math.sqrt(gamma * p_safe / rho_safe)

    if u_i <= 0.0 or abs(u_i) >= a_i:
        return np.array([rho_i, u_i, p_i, Y_i], dtype=float)

    p_ref = max(p_outlet, _PRESSURE_FLOOR)
    rho_ref = rho_safe * (p_ref / p_safe) ** (1.0 / gamma)
    T_ref = p_ref / (rho_ref * gas_constant)
    a_ref = math.sqrt(max(gamma * gas_constant * T_ref, 1e-12))

    if reflection_coeff is None:
        if impedance is None:
            R = 0.0
        else:
            z0 = rho_safe * a_i
            if impedance <= 0.0:
                _OUTLET_FALLBACK_COUNT += 1
                logger.error("Outlet impedance invalid; falling back to non_reflecting")
                if _OUTLET_FALLBACK_COUNT > _OUTLET_FALLBACK_LIMIT:
                    raise ValueError("Outlet impedance fallback limit exceeded")
                return _outlet_primitive(prim_i, p_outlet, gamma)
            R = (impedance - z0) / (impedance + z0)
    else:
        R = reflection_coeff

    if not math.isfinite(R) or abs(R) > 1.0:
        _OUTLET_FALLBACK_COUNT += 1
        logger.error("Outlet reflection coefficient invalid; falling back to non_reflecting")
        if _OUTLET_FALLBACK_COUNT > _OUTLET_FALLBACK_LIMIT:
            raise ValueError("Outlet reflection fallback limit exceeded")
        return _outlet_primitive(prim_i, p_outlet, gamma)

    J_plus = u_i + 2.0 * a_i / (gamma - 1.0)
    J_plus_ref = 2.0 * a_ref / (gamma - 1.0)
    J_minus_ref = -J_plus_ref
    J_minus = J_minus_ref + R * (J_plus - J_plus_ref)
    u_out = 0.5 * (J_plus + J_minus)
    a_out = 0.25 * (gamma - 1.0) * (J_plus - J_minus)
    if a_out <= 0.0 or not math.isfinite(a_out) or not math.isfinite(u_out):
        _OUTLET_FALLBACK_COUNT += 1
        logger.error("Outlet impedance produced invalid state; falling back to non_reflecting")
        if _OUTLET_FALLBACK_COUNT > _OUTLET_FALLBACK_LIMIT:
            raise ValueError("Outlet impedance fallback limit exceeded")
        return _outlet_primitive(prim_i, p_outlet, gamma)

    T_out = a_out * a_out / (gamma * gas_constant)
    p_out = p_ref * (T_out / T_ref) ** (gamma / (gamma - 1.0))
    if p_out <= 0.0 or T_out <= 0.0:
        _OUTLET_FALLBACK_COUNT += 1
        logger.error("Outlet impedance produced nonphysical p/T; falling back to non_reflecting")
        if _OUTLET_FALLBACK_COUNT > _OUTLET_FALLBACK_LIMIT:
            raise ValueError("Outlet impedance fallback limit exceeded")
        return _outlet_primitive(prim_i, p_outlet, gamma)
    rho_out = p_out / (gas_constant * T_out)
    return np.array([rho_out, u_out, p_out, Y_i], dtype=float)


def muscl_hancock_step(
    U: np.ndarray,
    dx: float,
    dt: float,
    gamma: float,
    gas_constant: float,
    friction_factor: float = 0.0,
    diameter: float = 1.0,
    p_outlet: float | None = None,
    outlet_mode: str | None = None,
    reflection_coeff: float | None = None,
    impedance: float | None = None,
    friction_model: str | None = None,
    roughness: float = 0.0,
    mu: float = 1.8e-5,
) -> np.ndarray:
    """Advance one step with MUSCL-Hancock + Rusanov."""

    N = U.shape[0]
    _guard_state(U, gamma, gas_constant, "muscl_hancock_step input")
    mode = outlet_mode
    if mode is None:
        mode = "non_reflecting" if p_outlet is not None else "copy"
    if p_outlet is None and mode != "copy":
        raise ValueError("p_outlet must be set when outlet_mode is not 'copy'")

    prim_full = conserved_to_primitive(U, gamma, gas_constant)
    rho_rec = np.maximum(prim_full[:, 0], _DENSITY_FLOOR)
    prim = np.stack([rho_rec, prim_full[:, 1], prim_full[:, 2], prim_full[:, 4]], axis=1)
    prim_ext = np.zeros((N + 2, 4))
    prim_ext[1:-1] = prim
    prim_ext[0] = prim[0]
    if mode == "copy":
        prim_ext[-1] = prim[-1]
    else:
        prim_ext[-1] = _outlet_primitive_bc(
            prim[-1], float(p_outlet), gamma, gas_constant, mode, reflection_coeff, impedance
        )

    dP_plus = prim_ext[2:] - prim_ext[1:-1]
    dP_minus = prim_ext[1:-1] - prim_ext[:-2]
    slopes = minmod(dP_minus, dP_plus)

    prim_L = prim - 0.5 * slopes
    prim_R = prim + 0.5 * slopes

    U_L = _primitive_to_conserved(prim_L, gamma, gas_constant, "muscl_hancock_step predictor L")
    U_R = _primitive_to_conserved(prim_R, gamma, gas_constant, "muscl_hancock_step predictor R")
    UL_face = np.zeros((N + 1, 4))
    UR_face = np.zeros((N + 1, 4))
    UL_face[1:-1] = U_R[:-1]
    UR_face[1:-1] = U_L[1:]
    UL_face[0] = U_L[0]
    UR_face[0] = U_L[0]
    if mode == "copy":
        UL_face[-1] = U_R[-1]
        UR_face[-1] = U_R[-1]
    else:
        prim_out = prim_ext[-1]
        if np.allclose(prim_out, prim[-1]):
            U_out = U_R[-1]
        else:
            U_out = _primitive_to_conserved_row(prim_out, gamma, gas_constant)
        UL_face[-1] = U_R[-1]
        UR_face[-1] = U_out

    F_face = _rusanov_flux(UL_face, UR_face, gamma, gas_constant)
    U_half = U - 0.5 * dt / dx * (F_face[1:] - F_face[:-1])
    _guard_state(U_half, gamma, gas_constant, "muscl_hancock_step predictor")

    prim_half_full = conserved_to_primitive(U_half, gamma, gas_constant)
    rho_half_rec = np.maximum(prim_half_full[:, 0], _DENSITY_FLOOR)
    prim_half = np.stack(
        [rho_half_rec, prim_half_full[:, 1], prim_half_full[:, 2], prim_half_full[:, 4]],
        axis=1,
    )
    prim_half_ext = np.zeros((N + 2, 4))
    prim_half_ext[1:-1] = prim_half
    prim_half_ext[0] = prim_half[0]
    if mode == "copy":
        prim_half_ext[-1] = prim_half[-1]
    else:
        prim_half_ext[-1] = _outlet_primitive_bc(
            prim_half[-1], float(p_outlet), gamma, gas_constant, mode, reflection_coeff, impedance
        )

    dP_plus = prim_half_ext[2:] - prim_half_ext[1:-1]
    dP_minus = prim_half_ext[1:-1] - prim_half_ext[:-2]
    slopes_half = minmod(dP_minus, dP_plus)

    prim_half_L = prim_half - 0.5 * slopes_half
    prim_half_R = prim_half + 0.5 * slopes_half

    U_half_L = _primitive_to_conserved(prim_half_L, gamma, gas_constant, "muscl_hancock_step corrector L")
    U_half_R = _primitive_to_conserved(prim_half_R, gamma, gas_constant, "muscl_hancock_step corrector R")

    UL_face = np.zeros((N + 1, 4))
    UR_face = np.zeros((N + 1, 4))
    UL_face[1:-1] = U_half_R[:-1]
    UR_face[1:-1] = U_half_L[1:]
    UL_face[0] = U_half_L[0]
    UR_face[0] = U_half_L[0]
    if mode == "copy":
        UL_face[-1] = U_half_R[-1]
        UR_face[-1] = U_half_R[-1]
    else:
        prim_out_half = prim_half_ext[-1]
        if np.allclose(prim_out_half, prim_half[-1]):
            U_out_half = U_half_R[-1]
        else:
            U_out_half = _primitive_to_conserved_row(prim_out_half, gamma, gas_constant)
        UL_face[-1] = U_half_R[-1]
        UR_face[-1] = U_out_half

    F_star = _rusanov_flux(UL_face, UR_face, gamma, gas_constant)
    U_new = U - dt / dx * (F_star[1:] - F_star[:-1])

    if friction_model is None:
        use_friction = friction_factor > 0.0
    else:
        use_friction = True

    if use_friction:
        if friction_model is None:
            f = friction_factor
        elif friction_model == "swamee-jain":
            if mu <= 0.0:
                raise ValueError("mu must be positive for friction_model")
            rho = U_new[:, 0]
            rho_safe = np.maximum(rho, 1e-12)
            u = U_new[:, 1] / rho_safe
            Re = rho_safe * np.abs(u) * diameter / mu
            f = _friction_factor_swamee_jain(Re, roughness, diameter)
        else:
            raise ValueError(f"Unknown friction_model '{friction_model}'")
        rho = U_new[:, 0]
        rho_safe = np.maximum(rho, 1e-12)
        u = U_new[:, 1] / rho_safe
        S_mom = -(f / (2.0 * diameter)) * rho * u * np.abs(u)
        U_new[:, 1] += dt * S_mom
        U_new[:, 2] += dt * u * S_mom

    _guard_state(U_new, gamma, gas_constant, "muscl_hancock_step output")
    _apply_scalar_guard(U_new, "muscl_hancock_step post-guard")
    return U_new


def cfl_dt(U: np.ndarray, dx: float, gamma: float, gas_constant: float, cfl: float, dt_max: float) -> float:
    _guard_state(U, gamma, gas_constant, "cfl_dt input")
    prim = conserved_to_primitive(U, gamma, gas_constant)
    rho_safe = np.maximum(prim[:, 0], _DENSITY_FLOOR)
    p_safe = np.maximum(prim[:, 2], _PRESSURE_FLOOR)
    a = np.sqrt(gamma * p_safe / rho_safe)
    max_speed = np.max(np.abs(prim[:, 1]) + a)
    return min(dt_max, cfl * dx / max(max_speed, 1e-9))
