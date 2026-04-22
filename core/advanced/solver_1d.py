from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np

from core.advanced.limiters import minmod

try:
    from numba import njit
    _HAS_NUMBA = True
except Exception:  # pragma: no cover - optional dependency
    _HAS_NUMBA = False

    def njit(*_args, **_kwargs):
        def wrapper(func):
            return func

        return wrapper

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
_NUMBA_BUFFERS: dict[int, dict[str, np.ndarray]] = {}


@dataclass
class ShockCFLSubstepsConfig:
    enabled: bool = True
    max_substeps: int = 6

    @classmethod
    def from_dict(cls, data: dict) -> "ShockCFLSubstepsConfig":
        return cls(
            enabled=bool(data.get("enabled", True)),
            max_substeps=int(data.get("max_substeps", 6)),
        )


@dataclass
class ShockCFLConfig:
    enabled: bool = False
    k: float = 8.0
    min_factor: float = 0.25
    sensor: str = "dp_over_p"
    p_floor: float = 1.0
    substeps: ShockCFLSubstepsConfig = field(default_factory=ShockCFLSubstepsConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "ShockCFLConfig":
        return cls(
            enabled=bool(data.get("enabled", False)),
            k=float(data.get("k", 8.0)),
            min_factor=float(data.get("min_factor", 0.25)),
            sensor=str(data.get("sensor", "dp_over_p")),
            p_floor=float(data.get("p_floor", 1.0)),
            substeps=ShockCFLSubstepsConfig.from_dict(data.get("substeps", {})),
        )


def validate_shock_cfl_config(cfg: ShockCFLConfig) -> None:
    if not cfg.enabled:
        return
    if cfg.k < 0.0:
        raise ValueError("shock_cfl.k must be non-negative")
    if not (0.0 < cfg.min_factor <= 1.0):
        raise ValueError("shock_cfl.min_factor must be in (0, 1]")
    if cfg.sensor not in ("dp_over_p", "du_over_a"):
        raise ValueError("shock_cfl.sensor must be 'dp_over_p' or 'du_over_a'")
    if cfg.p_floor <= 0.0:
        raise ValueError("shock_cfl.p_floor must be positive")
    if cfg.substeps.max_substeps < 1:
        raise ValueError("shock_cfl.substeps.max_substeps must be >= 1")

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
            denom = max(abs(rho_old), _DENSITY_FLOOR)
            Y_old = rhoY_old / denom
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


def _muscl_hancock_step_aos(
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
    friction_energy_mode: str = "wall_loss",
) -> np.ndarray:
    """Advance one step with MUSCL-Hancock + Rusanov (AoS reference)."""

    N = U.shape[0]
    if N < 3:
        raise ValueError("U must include left/right ghost cells and at least one physical cell")
    n_phys = N - 2
    _guard_state(U, gamma, gas_constant, "muscl_hancock_step input")
    mode = outlet_mode
    if mode is None:
        mode = "non_reflecting" if p_outlet is not None else "copy"
    if p_outlet is None and mode != "copy":
        raise ValueError("p_outlet must be set when outlet_mode is not 'copy'")

    U_phys = U[1:-1]
    prim_full = conserved_to_primitive(U_phys, gamma, gas_constant)
    rho_rec = np.maximum(prim_full[:, 0], _DENSITY_FLOOR)
    prim = np.stack([rho_rec, prim_full[:, 1], prim_full[:, 2], prim_full[:, 4]], axis=1)

    prim_left_full = conserved_to_primitive(U[0:1], gamma, gas_constant)[0]
    prim_left = np.array(
        [
            max(float(prim_left_full[0]), _DENSITY_FLOOR),
            float(prim_left_full[1]),
            max(float(prim_left_full[2]), _PRESSURE_FLOOR),
            float(prim_left_full[4]),
        ],
        dtype=float,
    )

    if mode == "copy":
        prim_right_full = conserved_to_primitive(U[-1:], gamma, gas_constant)[0]
        prim_right = np.array(
            [
                max(float(prim_right_full[0]), _DENSITY_FLOOR),
                float(prim_right_full[1]),
                max(float(prim_right_full[2]), _PRESSURE_FLOOR),
                float(prim_right_full[4]),
            ],
            dtype=float,
        )
    else:
        prim_right = _outlet_primitive_bc(
            prim[-1], float(p_outlet), gamma, gas_constant, mode, reflection_coeff, impedance
        )

    prim_ext = np.zeros((n_phys + 2, 4))
    prim_ext[0] = prim_left
    prim_ext[1:-1] = prim
    prim_ext[-1] = prim_right

    dP_plus = prim_ext[2:] - prim_ext[1:-1]
    dP_minus = prim_ext[1:-1] - prim_ext[:-2]
    slopes = minmod(dP_minus, dP_plus)

    prim_L = prim - 0.5 * slopes
    prim_R = prim + 0.5 * slopes

    U_L = _primitive_to_conserved(prim_L, gamma, gas_constant, "muscl_hancock_step predictor L")
    U_R = _primitive_to_conserved(prim_R, gamma, gas_constant, "muscl_hancock_step predictor R")
    U_ghost_left = _primitive_to_conserved_row(prim_left, gamma, gas_constant)
    U_ghost_right = _primitive_to_conserved_row(prim_right, gamma, gas_constant)
    UL_face = np.zeros((n_phys + 1, 4))
    UR_face = np.zeros((n_phys + 1, 4))
    UL_face[0] = U_ghost_left
    UR_face[0] = U_L[0]
    UL_face[1:-1] = U_R[:-1]
    UR_face[1:-1] = U_L[1:]
    UL_face[-1] = U_R[-1]
    UR_face[-1] = U_ghost_right

    F_face = _rusanov_flux(UL_face, UR_face, gamma, gas_constant)
    U_half_phys = U_phys - 0.5 * dt / dx * (F_face[1:] - F_face[:-1])
    U_half = U.copy()
    U_half[1:-1] = U_half_phys
    U_half[0] = U_ghost_left
    U_half[-1] = U_ghost_right
    _guard_state(U_half, gamma, gas_constant, "muscl_hancock_step predictor")
    U_half_phys = U_half[1:-1]

    prim_half_full = conserved_to_primitive(U_half_phys, gamma, gas_constant)
    rho_half_rec = np.maximum(prim_half_full[:, 0], _DENSITY_FLOOR)
    prim_half = np.stack(
        [rho_half_rec, prim_half_full[:, 1], prim_half_full[:, 2], prim_half_full[:, 4]],
        axis=1,
    )
    prim_half_left_full = conserved_to_primitive(U_half[0:1], gamma, gas_constant)[0]
    prim_half_left = np.array(
        [
            max(float(prim_half_left_full[0]), _DENSITY_FLOOR),
            float(prim_half_left_full[1]),
            max(float(prim_half_left_full[2]), _PRESSURE_FLOOR),
            float(prim_half_left_full[4]),
        ],
        dtype=float,
    )
    if mode == "copy":
        prim_half_right_full = conserved_to_primitive(U_half[-1:], gamma, gas_constant)[0]
        prim_half_right = np.array(
            [
                max(float(prim_half_right_full[0]), _DENSITY_FLOOR),
                float(prim_half_right_full[1]),
                max(float(prim_half_right_full[2]), _PRESSURE_FLOOR),
                float(prim_half_right_full[4]),
            ],
            dtype=float,
        )
    else:
        prim_half_right = _outlet_primitive_bc(
            prim_half[-1], float(p_outlet), gamma, gas_constant, mode, reflection_coeff, impedance
        )
    prim_half_ext = np.zeros((n_phys + 2, 4))
    prim_half_ext[0] = prim_half_left
    prim_half_ext[1:-1] = prim_half
    prim_half_ext[-1] = prim_half_right

    dP_plus = prim_half_ext[2:] - prim_half_ext[1:-1]
    dP_minus = prim_half_ext[1:-1] - prim_half_ext[:-2]
    slopes_half = minmod(dP_minus, dP_plus)

    prim_half_L = prim_half - 0.5 * slopes_half
    prim_half_R = prim_half + 0.5 * slopes_half

    U_half_L = _primitive_to_conserved(prim_half_L, gamma, gas_constant, "muscl_hancock_step corrector L")
    U_half_R = _primitive_to_conserved(prim_half_R, gamma, gas_constant, "muscl_hancock_step corrector R")

    U_ghost_left_half = _primitive_to_conserved_row(prim_half_left, gamma, gas_constant)
    U_ghost_right_half = _primitive_to_conserved_row(prim_half_right, gamma, gas_constant)
    UL_face = np.zeros((n_phys + 1, 4))
    UR_face = np.zeros((n_phys + 1, 4))
    UL_face[0] = U_ghost_left_half
    UR_face[0] = U_half_L[0]
    UL_face[1:-1] = U_half_R[:-1]
    UR_face[1:-1] = U_half_L[1:]
    UL_face[-1] = U_half_R[-1]
    UR_face[-1] = U_ghost_right_half

    F_star = _rusanov_flux(UL_face, UR_face, gamma, gas_constant)
    U_new_phys = U_phys - dt / dx * (F_star[1:] - F_star[:-1])

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
            rho = U_new_phys[:, 0]
            rho_safe = np.maximum(rho, 1e-12)
            u = U_new_phys[:, 1] / rho_safe
            Re = rho_safe * np.abs(u) * diameter / mu
            f = _friction_factor_swamee_jain(Re, roughness, diameter)
        else:
            raise ValueError(f"Unknown friction_model '{friction_model}'")
        rho = U_new_phys[:, 0]
        rho_safe = np.maximum(rho, 1e-12)
        u = U_new_phys[:, 1] / rho_safe
        S_mom = -(f / (2.0 * diameter)) * rho * u * np.abs(u)
        U_new_phys[:, 1] += dt * S_mom
        if friction_energy_mode == "wall_loss":
            U_new_phys[:, 2] += dt * u * S_mom
        elif friction_energy_mode != "adiabatic":
            raise ValueError(f"Unknown friction_energy_mode '{friction_energy_mode}'")

    U_new = U.copy()
    U_new[1:-1] = U_new_phys
    U_new[0] = U[0]
    if mode == "copy":
        U_new[-1] = U_new[-2]
    else:
        prim_new_full = conserved_to_primitive(U_new[1:-1], gamma, gas_constant)
        prim_new_right = np.array(
            [
                max(float(prim_new_full[-1, 0]), _DENSITY_FLOOR),
                float(prim_new_full[-1, 1]),
                max(float(prim_new_full[-1, 2]), _PRESSURE_FLOOR),
                float(prim_new_full[-1, 4]),
            ],
            dtype=float,
        )
        prim_new_right = _outlet_primitive_bc(
            prim_new_right, float(p_outlet), gamma, gas_constant, mode, reflection_coeff, impedance
        )
        U_new[-1] = _primitive_to_conserved_row(prim_new_right, gamma, gas_constant)

    _guard_state(U_new, gamma, gas_constant, "muscl_hancock_step output")
    _apply_scalar_guard(U_new, "muscl_hancock_step post-guard")
    return U_new


def _reconstruct_primitives_soa(
    prim_left: np.ndarray,
    prim_right: np.ndarray,
    rho: np.ndarray,
    u: np.ndarray,
    p: np.ndarray,
    Y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    rho_ext = np.empty(rho.size + 2)
    u_ext = np.empty_like(rho_ext)
    p_ext = np.empty_like(rho_ext)
    Y_ext = np.empty_like(rho_ext)
    rho_ext[0] = prim_left[0]
    u_ext[0] = prim_left[1]
    p_ext[0] = prim_left[2]
    Y_ext[0] = prim_left[3]
    rho_ext[1:-1] = rho
    u_ext[1:-1] = u
    p_ext[1:-1] = p
    Y_ext[1:-1] = Y
    rho_ext[-1] = prim_right[0]
    u_ext[-1] = prim_right[1]
    p_ext[-1] = prim_right[2]
    Y_ext[-1] = prim_right[3]

    slope_rho = minmod(rho_ext[1:-1] - rho_ext[:-2], rho_ext[2:] - rho_ext[1:-1])
    slope_u = minmod(u_ext[1:-1] - u_ext[:-2], u_ext[2:] - u_ext[1:-1])
    slope_p = minmod(p_ext[1:-1] - p_ext[:-2], p_ext[2:] - p_ext[1:-1])
    slope_Y = minmod(Y_ext[1:-1] - Y_ext[:-2], Y_ext[2:] - Y_ext[1:-1])

    prim_L = np.stack(
        [rho - 0.5 * slope_rho, u - 0.5 * slope_u, p - 0.5 * slope_p, Y - 0.5 * slope_Y],
        axis=1,
    )
    prim_R = np.stack(
        [rho + 0.5 * slope_rho, u + 0.5 * slope_u, p + 0.5 * slope_p, Y + 0.5 * slope_Y],
        axis=1,
    )
    return prim_L, prim_R


def _get_numba_buffers(n_phys: int) -> dict[str, np.ndarray]:
    buf = _NUMBA_BUFFERS.get(n_phys)
    if buf is None:
        buf = {
            "prim": np.empty((n_phys, 4)),
            "prim_ext": np.empty((n_phys + 2, 4)),
            "slope": np.empty((n_phys, 4)),
            "prim_L": np.empty((n_phys, 4)),
            "prim_R": np.empty((n_phys, 4)),
            "U_L": np.empty((n_phys, 4)),
            "U_R": np.empty((n_phys, 4)),
            "F_face": np.empty((n_phys + 1, 4)),
            "U_half": np.empty((n_phys, 4)),
            "prim_half": np.empty((n_phys, 4)),
            "prim_half_ext": np.empty((n_phys + 2, 4)),
            "slope_half": np.empty((n_phys, 4)),
            "prim_half_L": np.empty((n_phys, 4)),
            "prim_half_R": np.empty((n_phys, 4)),
            "U_half_L": np.empty((n_phys, 4)),
            "U_half_R": np.empty((n_phys, 4)),
            "F_star": np.empty((n_phys + 1, 4)),
            "U_out": np.empty((n_phys, 4)),
        }
        _NUMBA_BUFFERS[n_phys] = buf
    return buf


@njit(cache=True)
def _minmod_numba(a: float, b: float) -> float:
    if a * b <= 0.0:
        return 0.0
    if abs(a) < abs(b):
        return a
    return b


@njit(cache=True)
def _muscl_hancock_step_soa_numba_kernel(
    U_in: np.ndarray,
    ghost_left_prim: np.ndarray,
    ghost_right_prim: np.ndarray,
    ghost_left_U: np.ndarray,
    ghost_right_U: np.ndarray,
    dx: float,
    dt: float,
    gamma: float,
    gas_constant: float,
    friction_model: int,
    friction_factor: float,
    roughness: float,
    diameter: float,
    mu: float,
    friction_energy_mode: int,
    prim: np.ndarray,
    prim_ext: np.ndarray,
    slope: np.ndarray,
    prim_L: np.ndarray,
    prim_R: np.ndarray,
    U_L: np.ndarray,
    U_R: np.ndarray,
    F_face: np.ndarray,
    U_half: np.ndarray,
    prim_half: np.ndarray,
    prim_half_ext: np.ndarray,
    slope_half: np.ndarray,
    prim_half_L: np.ndarray,
    prim_half_R: np.ndarray,
    U_half_L: np.ndarray,
    U_half_R: np.ndarray,
    F_star: np.ndarray,
    U_out: np.ndarray,
) -> None:
    n_phys = U_in.shape[0]

    for i in range(n_phys):
        rho = U_in[i, 0]
        rho_safe = rho if rho > _DENSITY_FLOOR else _DENSITY_FLOOR
        u = U_in[i, 1] / rho_safe
        E = U_in[i, 2] / rho_safe
        e_int = E - 0.5 * u * u
        T = (gamma - 1.0) * e_int / gas_constant
        if T < 1e-9:
            T = 1e-9
        p = rho_safe * gas_constant * T
        Y = U_in[i, 3] / rho_safe
        prim[i, 0] = rho_safe
        prim[i, 1] = u
        prim[i, 2] = p
        prim[i, 3] = Y

    prim_ext[0, :] = ghost_left_prim
    prim_ext[1:-1, :] = prim
    prim_ext[-1, :] = ghost_right_prim

    for i in range(n_phys):
        for j in range(4):
            a = prim_ext[i + 1, j] - prim_ext[i, j]
            b = prim_ext[i + 2, j] - prim_ext[i + 1, j]
            slope[i, j] = _minmod_numba(a, b)

    for i in range(n_phys):
        for j in range(4):
            prim_L[i, j] = prim[i, j] - 0.5 * slope[i, j]
            prim_R[i, j] = prim[i, j] + 0.5 * slope[i, j]

    for i in range(n_phys):
        for arr_in, arr_out in (
            (prim_L, U_L),
            (prim_R, U_R),
        ):
            rho = arr_in[i, 0]
            if rho <= 0.0:
                rho = _DENSITY_FLOOR
            u = arr_in[i, 1]
            p = arr_in[i, 2]
            if p <= 0.0:
                p = _PRESSURE_FLOOR
            Y = arr_in[i, 3]
            T = p / (rho * gas_constant)
            e_int = gas_constant * T / (gamma - 1.0)
            E = e_int + 0.5 * u * u
            arr_out[i, 0] = rho
            arr_out[i, 1] = rho * u
            arr_out[i, 2] = rho * E
            arr_out[i, 3] = rho * Y

    for i in range(n_phys + 1):
        if i == 0:
            UL = ghost_left_U
            UR = U_L[0]
        elif i == n_phys:
            UL = U_R[-1]
            UR = ghost_right_U
        else:
            UL = U_R[i - 1]
            UR = U_L[i]

        rhoL = UL[0]
        rhoR = UR[0]
        rhoL_safe = rhoL if rhoL > _DENSITY_FLOOR else _DENSITY_FLOOR
        rhoR_safe = rhoR if rhoR > _DENSITY_FLOOR else _DENSITY_FLOOR
        uL = UL[1] / rhoL_safe
        uR = UR[1] / rhoR_safe
        pL = (gamma - 1.0) * (UL[2] - 0.5 * rhoL_safe * uL * uL)
        pR = (gamma - 1.0) * (UR[2] - 0.5 * rhoR_safe * uR * uR)
        if pL < _PRESSURE_FLOOR:
            pL = _PRESSURE_FLOOR
        if pR < _PRESSURE_FLOOR:
            pR = _PRESSURE_FLOOR
        aL = math.sqrt(gamma * pL / rhoL_safe)
        aR = math.sqrt(gamma * pR / rhoR_safe)
        smax = max(abs(uL) + aL, abs(uR) + aR)

        F0L = rhoL * uL
        F1L = rhoL * uL * uL + pL
        F2L = uL * (UL[2] + pL)
        F3L = UL[3] * uL
        F0R = rhoR * uR
        F1R = rhoR * uR * uR + pR
        F2R = uR * (UR[2] + pR)
        F3R = UR[3] * uR

        F_face[i, 0] = 0.5 * (F0L + F0R) - 0.5 * smax * (UR[0] - UL[0])
        F_face[i, 1] = 0.5 * (F1L + F1R) - 0.5 * smax * (UR[1] - UL[1])
        F_face[i, 2] = 0.5 * (F2L + F2R) - 0.5 * smax * (UR[2] - UL[2])
        F_face[i, 3] = 0.5 * (F3L + F3R) - 0.5 * smax * (UR[3] - UL[3])

    for i in range(n_phys):
        U_half[i, 0] = U_in[i, 0] - 0.5 * dt / dx * (F_face[i + 1, 0] - F_face[i, 0])
        U_half[i, 1] = U_in[i, 1] - 0.5 * dt / dx * (F_face[i + 1, 1] - F_face[i, 1])
        U_half[i, 2] = U_in[i, 2] - 0.5 * dt / dx * (F_face[i + 1, 2] - F_face[i, 2])
        U_half[i, 3] = U_in[i, 3] - 0.5 * dt / dx * (F_face[i + 1, 3] - F_face[i, 3])

    for i in range(n_phys):
        rho = U_half[i, 0]
        rho_safe = rho if rho > _DENSITY_FLOOR else _DENSITY_FLOOR
        u = U_half[i, 1] / rho_safe
        E = U_half[i, 2] / rho_safe
        e_int = E - 0.5 * u * u
        T = (gamma - 1.0) * e_int / gas_constant
        if T < 1e-9:
            T = 1e-9
        p = rho_safe * gas_constant * T
        Y = U_half[i, 3] / rho_safe
        prim_half[i, 0] = rho_safe
        prim_half[i, 1] = u
        prim_half[i, 2] = p
        prim_half[i, 3] = Y

    prim_half_ext[0, :] = ghost_left_prim
    prim_half_ext[1:-1, :] = prim_half
    prim_half_ext[-1, :] = ghost_right_prim

    for i in range(n_phys):
        for j in range(4):
            a = prim_half_ext[i + 1, j] - prim_half_ext[i, j]
            b = prim_half_ext[i + 2, j] - prim_half_ext[i + 1, j]
            slope_half[i, j] = _minmod_numba(a, b)

    for i in range(n_phys):
        for j in range(4):
            prim_half_L[i, j] = prim_half[i, j] - 0.5 * slope_half[i, j]
            prim_half_R[i, j] = prim_half[i, j] + 0.5 * slope_half[i, j]

    for i in range(n_phys):
        for arr_in, arr_out in (
            (prim_half_L, U_half_L),
            (prim_half_R, U_half_R),
        ):
            rho = arr_in[i, 0]
            if rho <= 0.0:
                rho = _DENSITY_FLOOR
            u = arr_in[i, 1]
            p = arr_in[i, 2]
            if p <= 0.0:
                p = _PRESSURE_FLOOR
            Y = arr_in[i, 3]
            T = p / (rho * gas_constant)
            e_int = gas_constant * T / (gamma - 1.0)
            E = e_int + 0.5 * u * u
            arr_out[i, 0] = rho
            arr_out[i, 1] = rho * u
            arr_out[i, 2] = rho * E
            arr_out[i, 3] = rho * Y

    for i in range(n_phys + 1):
        if i == 0:
            UL = ghost_left_U
            UR = U_half_L[0]
        elif i == n_phys:
            UL = U_half_R[-1]
            UR = ghost_right_U
        else:
            UL = U_half_R[i - 1]
            UR = U_half_L[i]

        rhoL = UL[0]
        rhoR = UR[0]
        rhoL_safe = rhoL if rhoL > _DENSITY_FLOOR else _DENSITY_FLOOR
        rhoR_safe = rhoR if rhoR > _DENSITY_FLOOR else _DENSITY_FLOOR
        uL = UL[1] / rhoL_safe
        uR = UR[1] / rhoR_safe
        pL = (gamma - 1.0) * (UL[2] - 0.5 * rhoL_safe * uL * uL)
        pR = (gamma - 1.0) * (UR[2] - 0.5 * rhoR_safe * uR * uR)
        if pL < _PRESSURE_FLOOR:
            pL = _PRESSURE_FLOOR
        if pR < _PRESSURE_FLOOR:
            pR = _PRESSURE_FLOOR
        aL = math.sqrt(gamma * pL / rhoL_safe)
        aR = math.sqrt(gamma * pR / rhoR_safe)
        smax = max(abs(uL) + aL, abs(uR) + aR)

        F0L = rhoL * uL
        F1L = rhoL * uL * uL + pL
        F2L = uL * (UL[2] + pL)
        F3L = UL[3] * uL
        F0R = rhoR * uR
        F1R = rhoR * uR * uR + pR
        F2R = uR * (UR[2] + pR)
        F3R = UR[3] * uR

        F_star[i, 0] = 0.5 * (F0L + F0R) - 0.5 * smax * (UR[0] - UL[0])
        F_star[i, 1] = 0.5 * (F1L + F1R) - 0.5 * smax * (UR[1] - UL[1])
        F_star[i, 2] = 0.5 * (F2L + F2R) - 0.5 * smax * (UR[2] - UL[2])
        F_star[i, 3] = 0.5 * (F3L + F3R) - 0.5 * smax * (UR[3] - UL[3])

    for i in range(n_phys):
        U_out[i, 0] = U_in[i, 0] - dt / dx * (F_star[i + 1, 0] - F_star[i, 0])
        U_out[i, 1] = U_in[i, 1] - dt / dx * (F_star[i + 1, 1] - F_star[i, 1])
        U_out[i, 2] = U_in[i, 2] - dt / dx * (F_star[i + 1, 2] - F_star[i, 2])
        U_out[i, 3] = U_in[i, 3] - dt / dx * (F_star[i + 1, 3] - F_star[i, 3])

    if friction_model != 2:
        for i in range(n_phys):
            rho = U_out[i, 0]
            rho_safe = rho if rho > 1e-12 else 1e-12
            u = U_out[i, 1] / rho_safe
            if friction_model == 0:
                f = friction_factor
            else:
                Re = rho_safe * abs(u) * diameter / mu
                if Re < 1e-8:
                    Re = 1e-8
                rel_eps = roughness / diameter
                f_lam = 64.0 / Re
                term = rel_eps / 3.7 + 5.74 / (Re ** 0.9)
                f_turb = 0.25 / (math.log10(term) ** 2)
                if Re < 2300.0:
                    f = f_lam
                else:
                    f = f_turb
            S_mom = -(f / (2.0 * diameter)) * rho * u * abs(u)
            U_out[i, 1] = U_out[i, 1] + dt * S_mom
            if friction_energy_mode == 0:
                U_out[i, 2] = U_out[i, 2] + dt * u * S_mom


def _muscl_hancock_step_soa(
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
    friction_energy_mode: str = "wall_loss",
) -> np.ndarray:
    """Advance one step with MUSCL-Hancock + Rusanov (SoA prep)."""
    N = U.shape[0]
    if N < 3:
        raise ValueError("U must include left/right ghost cells and at least one physical cell")
    n_phys = N - 2
    _guard_state(U, gamma, gas_constant, "muscl_hancock_step input")
    mode = outlet_mode
    if mode is None:
        mode = "non_reflecting" if p_outlet is not None else "copy"
    if p_outlet is None and mode != "copy":
        raise ValueError("p_outlet must be set when outlet_mode is not 'copy'")

    U_phys = U[1:-1]
    prim_full = conserved_to_primitive(U_phys, gamma, gas_constant)
    rho = np.maximum(prim_full[:, 0], _DENSITY_FLOOR)
    u = prim_full[:, 1]
    p = prim_full[:, 2]
    Y = prim_full[:, 4]

    prim_left_full = conserved_to_primitive(U[0:1], gamma, gas_constant)[0]
    prim_left = np.array(
        [
            max(float(prim_left_full[0]), _DENSITY_FLOOR),
            float(prim_left_full[1]),
            max(float(prim_left_full[2]), _PRESSURE_FLOOR),
            float(prim_left_full[4]),
        ],
        dtype=float,
    )
    if mode == "copy":
        prim_right_full = conserved_to_primitive(U[-1:], gamma, gas_constant)[0]
        prim_right = np.array(
            [
                max(float(prim_right_full[0]), _DENSITY_FLOOR),
                float(prim_right_full[1]),
                max(float(prim_right_full[2]), _PRESSURE_FLOOR),
                float(prim_right_full[4]),
            ],
            dtype=float,
        )
    else:
        prim_right = _outlet_primitive_bc(
            np.array([rho[-1], u[-1], p[-1], Y[-1]], dtype=float),
            float(p_outlet),
            gamma,
            gas_constant,
            mode,
            reflection_coeff,
            impedance,
        )

    prim_L, prim_R = _reconstruct_primitives_soa(prim_left, prim_right, rho, u, p, Y)

    U_L = _primitive_to_conserved(prim_L, gamma, gas_constant, "muscl_hancock_step predictor L")
    U_R = _primitive_to_conserved(prim_R, gamma, gas_constant, "muscl_hancock_step predictor R")
    U_ghost_left = _primitive_to_conserved_row(prim_left, gamma, gas_constant)
    U_ghost_right = _primitive_to_conserved_row(prim_right, gamma, gas_constant)

    UL_face = np.zeros((n_phys + 1, 4))
    UR_face = np.zeros((n_phys + 1, 4))
    UL_face[0] = U_ghost_left
    UR_face[0] = U_L[0]
    UL_face[1:-1] = U_R[:-1]
    UR_face[1:-1] = U_L[1:]
    UL_face[-1] = U_R[-1]
    UR_face[-1] = U_ghost_right

    F_face = _rusanov_flux(UL_face, UR_face, gamma, gas_constant)
    U_half_phys = U_phys - 0.5 * dt / dx * (F_face[1:] - F_face[:-1])
    U_half = U.copy()
    U_half[1:-1] = U_half_phys
    U_half[0] = U_ghost_left
    U_half[-1] = U_ghost_right
    _guard_state(U_half, gamma, gas_constant, "muscl_hancock_step predictor")
    U_half_phys = U_half[1:-1]

    prim_half_full = conserved_to_primitive(U_half_phys, gamma, gas_constant)
    rho_half = np.maximum(prim_half_full[:, 0], _DENSITY_FLOOR)
    u_half = prim_half_full[:, 1]
    p_half = prim_half_full[:, 2]
    Y_half = prim_half_full[:, 4]

    prim_half_left_full = conserved_to_primitive(U_half[0:1], gamma, gas_constant)[0]
    prim_half_left = np.array(
        [
            max(float(prim_half_left_full[0]), _DENSITY_FLOOR),
            float(prim_half_left_full[1]),
            max(float(prim_half_left_full[2]), _PRESSURE_FLOOR),
            float(prim_half_left_full[4]),
        ],
        dtype=float,
    )
    if mode == "copy":
        prim_half_right_full = conserved_to_primitive(U_half[-1:], gamma, gas_constant)[0]
        prim_half_right = np.array(
            [
                max(float(prim_half_right_full[0]), _DENSITY_FLOOR),
                float(prim_half_right_full[1]),
                max(float(prim_half_right_full[2]), _PRESSURE_FLOOR),
                float(prim_half_right_full[4]),
            ],
            dtype=float,
        )
    else:
        prim_half_right = _outlet_primitive_bc(
            np.array([rho_half[-1], u_half[-1], p_half[-1], Y_half[-1]], dtype=float),
            float(p_outlet),
            gamma,
            gas_constant,
            mode,
            reflection_coeff,
            impedance,
        )

    prim_half_L, prim_half_R = _reconstruct_primitives_soa(
        prim_half_left, prim_half_right, rho_half, u_half, p_half, Y_half
    )

    U_half_L = _primitive_to_conserved(prim_half_L, gamma, gas_constant, "muscl_hancock_step corrector L")
    U_half_R = _primitive_to_conserved(prim_half_R, gamma, gas_constant, "muscl_hancock_step corrector R")
    U_ghost_left_half = _primitive_to_conserved_row(prim_half_left, gamma, gas_constant)
    U_ghost_right_half = _primitive_to_conserved_row(prim_half_right, gamma, gas_constant)

    UL_face = np.zeros((n_phys + 1, 4))
    UR_face = np.zeros((n_phys + 1, 4))
    UL_face[0] = U_ghost_left_half
    UR_face[0] = U_half_L[0]
    UL_face[1:-1] = U_half_R[:-1]
    UR_face[1:-1] = U_half_L[1:]
    UL_face[-1] = U_half_R[-1]
    UR_face[-1] = U_ghost_right_half

    F_star = _rusanov_flux(UL_face, UR_face, gamma, gas_constant)
    U_new_phys = U_phys - dt / dx * (F_star[1:] - F_star[:-1])

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
            rho_f = U_new_phys[:, 0]
            rho_safe = np.maximum(rho_f, 1e-12)
            u_f = U_new_phys[:, 1] / rho_safe
            Re = rho_safe * np.abs(u_f) * diameter / mu
            f = _friction_factor_swamee_jain(Re, roughness, diameter)
        else:
            raise ValueError(f"Unknown friction_model '{friction_model}'")
        rho_f = U_new_phys[:, 0]
        rho_safe = np.maximum(rho_f, 1e-12)
        u_f = U_new_phys[:, 1] / rho_safe
        S_mom = -(f / (2.0 * diameter)) * rho_f * u_f * np.abs(u_f)
        U_new_phys[:, 1] += dt * S_mom
        if friction_energy_mode == "wall_loss":
            U_new_phys[:, 2] += dt * u_f * S_mom
        elif friction_energy_mode != "adiabatic":
            raise ValueError(f"Unknown friction_energy_mode '{friction_energy_mode}'")

    U_new = U.copy()
    U_new[1:-1] = U_new_phys
    U_new[0] = U[0]
    if mode == "copy":
        U_new[-1] = U_new[-2]
    else:
        prim_new_full = conserved_to_primitive(U_new[1:-1], gamma, gas_constant)
        prim_new_right = np.array(
            [
                max(float(prim_new_full[-1, 0]), _DENSITY_FLOOR),
                float(prim_new_full[-1, 1]),
                max(float(prim_new_full[-1, 2]), _PRESSURE_FLOOR),
                float(prim_new_full[-1, 4]),
            ],
            dtype=float,
        )
        prim_new_right = _outlet_primitive_bc(
            prim_new_right, float(p_outlet), gamma, gas_constant, mode, reflection_coeff, impedance
        )
        U_new[-1] = _primitive_to_conserved_row(prim_new_right, gamma, gas_constant)

    _guard_state(U_new, gamma, gas_constant, "muscl_hancock_step output")
    _apply_scalar_guard(U_new, "muscl_hancock_step post-guard")
    return U_new


def _muscl_hancock_step_soa_numba(
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
    friction_energy_mode: str = "wall_loss",
) -> np.ndarray:
    if not _HAS_NUMBA:
        raise RuntimeError("Numba is not available")
    mode = outlet_mode
    if mode is None:
        mode = "non_reflecting" if p_outlet is not None else "copy"
    if mode != "copy" or p_outlet is not None:
        return _muscl_hancock_step_soa(
            U,
            dx,
            dt,
            gamma,
            gas_constant,
            friction_factor=friction_factor,
            diameter=diameter,
            p_outlet=p_outlet,
            outlet_mode=outlet_mode,
            reflection_coeff=reflection_coeff,
            impedance=impedance,
            friction_model=friction_model,
            roughness=roughness,
            mu=mu,
            friction_energy_mode=friction_energy_mode,
        )
    if friction_model is None:
        friction_mode_code = 0 if friction_factor > 0.0 else 2
    elif friction_model == "constant":
        friction_mode_code = 0
    elif friction_model == "swamee-jain":
        friction_mode_code = 1
    else:
        raise ValueError(f"Unknown friction_model '{friction_model}'")
    if friction_mode_code == 1:
        if mu <= 0.0:
            raise ValueError("mu must be positive for friction_model")
        if diameter <= 0.0:
            raise ValueError("diameter must be positive for friction_model")
    if friction_energy_mode == "wall_loss":
        friction_energy_code = 0
    elif friction_energy_mode == "adiabatic":
        friction_energy_code = 1
    else:
        raise ValueError(f"Unknown friction_energy_mode '{friction_energy_mode}'")

    N = U.shape[0]
    if N < 3:
        raise ValueError("U must include left/right ghost cells and at least one physical cell")
    n_phys = N - 2
    _guard_state(U, gamma, gas_constant, "muscl_hancock_step input")

    U_phys = U[1:-1]
    prim_left_full = conserved_to_primitive(U[0:1], gamma, gas_constant)[0]
    prim_left = np.array(
        [
            max(float(prim_left_full[0]), _DENSITY_FLOOR),
            float(prim_left_full[1]),
            max(float(prim_left_full[2]), _PRESSURE_FLOOR),
            float(prim_left_full[4]),
        ],
        dtype=float,
    )
    prim_right_full = conserved_to_primitive(U[-1:], gamma, gas_constant)[0]
    prim_right = np.array(
        [
            max(float(prim_right_full[0]), _DENSITY_FLOOR),
            float(prim_right_full[1]),
            max(float(prim_right_full[2]), _PRESSURE_FLOOR),
            float(prim_right_full[4]),
        ],
        dtype=float,
    )
    ghost_left_U = _primitive_to_conserved_row(prim_left, gamma, gas_constant)
    ghost_right_U = _primitive_to_conserved_row(prim_right, gamma, gas_constant)

    buf = _get_numba_buffers(n_phys)
    _muscl_hancock_step_soa_numba_kernel(
        U_phys,
        prim_left,
        prim_right,
        ghost_left_U,
        ghost_right_U,
        dx,
        dt,
        gamma,
        gas_constant,
        friction_mode_code,
        friction_factor,
        roughness,
        diameter,
        mu,
        friction_energy_code,
        buf["prim"],
        buf["prim_ext"],
        buf["slope"],
        buf["prim_L"],
        buf["prim_R"],
        buf["U_L"],
        buf["U_R"],
        buf["F_face"],
        buf["U_half"],
        buf["prim_half"],
        buf["prim_half_ext"],
        buf["slope_half"],
        buf["prim_half_L"],
        buf["prim_half_R"],
        buf["U_half_L"],
        buf["U_half_R"],
        buf["F_star"],
        buf["U_out"],
    )

    U_new = U.copy()
    U_new[1:-1] = buf["U_out"]
    U_new[0] = U[0]
    U_new[-1] = U_new[-2]
    _guard_state(U_new, gamma, gas_constant, "muscl_hancock_step output")
    _apply_scalar_guard(U_new, "muscl_hancock_step post-guard")
    return U_new


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
    friction_energy_mode: str = "wall_loss",
    use_numba_1d: bool = False,
) -> np.ndarray:
    if use_numba_1d:
        return step_soa_numba(
            U,
            dx,
            dt,
            gamma,
            gas_constant,
            friction_factor=friction_factor,
            diameter=diameter,
            p_outlet=p_outlet,
            outlet_mode=outlet_mode,
            reflection_coeff=reflection_coeff,
            impedance=impedance,
            friction_model=friction_model,
            roughness=roughness,
            mu=mu,
            friction_energy_mode=friction_energy_mode,
        )
    return step_soa_python(
        U,
        dx,
        dt,
        gamma,
        gas_constant,
        friction_factor=friction_factor,
        diameter=diameter,
        p_outlet=p_outlet,
        outlet_mode=outlet_mode,
        reflection_coeff=reflection_coeff,
        impedance=impedance,
        friction_model=friction_model,
        roughness=roughness,
        mu=mu,
        friction_energy_mode=friction_energy_mode,
    )


def step_soa_python(
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
    friction_energy_mode: str = "wall_loss",
) -> np.ndarray:
    return _muscl_hancock_step_soa(
        U,
        dx,
        dt,
        gamma,
        gas_constant,
        friction_factor=friction_factor,
        diameter=diameter,
        p_outlet=p_outlet,
        outlet_mode=outlet_mode,
        reflection_coeff=reflection_coeff,
        impedance=impedance,
        friction_model=friction_model,
        roughness=roughness,
        mu=mu,
        friction_energy_mode=friction_energy_mode,
    )


def step_soa_numba(
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
    friction_energy_mode: str = "wall_loss",
) -> np.ndarray:
    if _HAS_NUMBA:
        return _muscl_hancock_step_soa_numba(
            U,
            dx,
            dt,
            gamma,
            gas_constant,
            friction_factor=friction_factor,
            diameter=diameter,
            p_outlet=p_outlet,
            outlet_mode=outlet_mode,
            reflection_coeff=reflection_coeff,
            impedance=impedance,
            friction_model=friction_model,
            roughness=roughness,
            mu=mu,
            friction_energy_mode=friction_energy_mode,
        )
    return _muscl_hancock_step_soa(
        U,
        dx,
        dt,
        gamma,
        gas_constant,
        friction_factor=friction_factor,
        diameter=diameter,
        p_outlet=p_outlet,
        outlet_mode=outlet_mode,
        reflection_coeff=reflection_coeff,
        impedance=impedance,
        friction_model=friction_model,
        roughness=roughness,
        mu=mu,
        friction_energy_mode=friction_energy_mode,
    )


def cfl_dt(
    U: np.ndarray,
    dx: float,
    gamma: float,
    gas_constant: float,
    cfl: float,
    dt_max: float,
    ghost_left: int = 1,
    ghost_right: int = 1,
) -> float:
    if not np.isfinite(U).all():
        raise ValueError("Non-finite state in cfl_dt input")
    if ghost_left < 0 or ghost_right < 0:
        raise ValueError("ghost_left/ghost_right must be non-negative")
    end = U.shape[0] - ghost_right
    if ghost_left >= end:
        raise ValueError("ghost_left/ghost_right exclude all cells")
    U_phys = U[ghost_left:end].copy()
    prim = conserved_to_primitive(U_phys, gamma, gas_constant)
    rho_safe = np.maximum(prim[:, 0], _DENSITY_FLOOR)
    p_safe = np.maximum(prim[:, 2], _PRESSURE_FLOOR)
    a = np.sqrt(gamma * p_safe / rho_safe)
    max_speed = np.max(np.abs(prim[:, 1]) + a)
    return min(dt_max, cfl * dx / max(max_speed, 1e-9))


def _shock_sensor_value(
    prim: np.ndarray,
    gamma: float,
    cfg: ShockCFLConfig,
) -> float:
    if prim.shape[0] < 3:
        return 0.0
    p = prim[:, 2]
    if cfg.sensor == "dp_over_p":
        denom = np.maximum(p[1:-1], cfg.p_floor)
        s = np.abs(p[2:] - p[:-2]) / denom
    else:
        rho = prim[:, 0]
        rho_safe = np.maximum(rho, _DENSITY_FLOOR)
        p_safe = np.maximum(p, _PRESSURE_FLOOR)
        a = np.sqrt(gamma * p_safe / rho_safe)
        denom = np.maximum(a[1:-1], 1e-9)
        u = prim[:, 1]
        s = np.abs(u[2:] - u[:-2]) / denom
    if s.size == 0:
        return 0.0
    return float(np.max(s))


def shock_cfl_factor(
    U: np.ndarray,
    gamma: float,
    gas_constant: float,
    cfg: ShockCFLConfig,
    ghost_left: int = 1,
    ghost_right: int = 1,
) -> float:
    if not cfg.enabled:
        return 1.0
    if ghost_left < 0 or ghost_right < 0:
        raise ValueError("ghost_left/ghost_right must be non-negative")
    end = U.shape[0] - ghost_right
    if ghost_left >= end:
        raise ValueError("ghost_left/ghost_right exclude all cells")
    U_phys = U[ghost_left:end].copy()
    prim = conserved_to_primitive(U_phys, gamma, gas_constant)
    s_max = _shock_sensor_value(prim, gamma, cfg)
    factor = 1.0 / (1.0 + cfg.k * s_max)
    return float(np.clip(factor, cfg.min_factor, 1.0))


def shock_cfl_plan(
    U: np.ndarray,
    dt_base: float,
    gamma: float,
    gas_constant: float,
    cfg: ShockCFLConfig,
    ghost_left: int = 1,
    ghost_right: int = 1,
) -> tuple[float, int]:
    if dt_base <= 0.0 or not cfg.enabled:
        return dt_base, 1
    factor = shock_cfl_factor(
        U,
        gamma,
        gas_constant,
        cfg,
        ghost_left=ghost_left,
        ghost_right=ghost_right,
    )
    dt_shock = dt_base * factor
    if not cfg.substeps.enabled or dt_shock >= dt_base:
        return dt_shock, 1
    n_sub = int(math.ceil(dt_base / max(dt_shock, 1e-12)))
    n_sub = max(1, min(n_sub, cfg.substeps.max_substeps))
    return dt_base, n_sub
