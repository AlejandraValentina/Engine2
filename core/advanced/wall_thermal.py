from __future__ import annotations

import math
from typing import Tuple

import numpy as np

from core.engine_components import WallThermalConfig

try:  # pragma: no cover - optional acceleration
    from numba import njit
    _NUMBA_AVAILABLE = True
except Exception:  # pragma: no cover - fallback when numba missing
    _NUMBA_AVAILABLE = False

    def njit(*args, **kwargs):
        def decorator(func):
            return func

        return decorator


_T_REF = 300.0
_SUTHERLAND_S = 110.4
_SMOOTH_RE_SPAN = 2000.0
_NU_LAMINAR = 3.66


@njit(cache=True)
def _mu_sutherland_numba(T: float, mu_ref: float) -> float:
    T_safe = max(T, 1e-6)
    T_ref = 273.15
    return mu_ref * (T_safe / T_ref) ** 1.5 * (T_ref + _SUTHERLAND_S) / (T_safe + _SUTHERLAND_S)


@njit(cache=True)
def _k_powerlaw_numba(T: float, k_ref: float) -> float:
    T_safe = max(T, 1e-6)
    return k_ref * (T_safe / _T_REF) ** 0.76


@njit(cache=True)
def _cp_powerlaw_numba(T: float, cp_ref: float) -> float:
    T_safe = max(T, 1e-6)
    return cp_ref * (T_safe / _T_REF) ** 0.03


@njit(cache=True)
def _dittus_boelter_h_array_numba(
    T: np.ndarray,
    rho: np.ndarray,
    u: np.ndarray,
    diameter_m: float,
    mu_ref: float,
    k_ref: float,
    cp_ref: float,
    pr_const: float,
    mu_model_flag: int,
    h_min: float,
    h_max: float,
) -> np.ndarray:
    n = T.shape[0]
    out = np.empty(n, dtype=np.float64)
    diameter = max(diameter_m, 1e-9)
    for i in range(n):
        Ti = T[i]
        if mu_model_flag == 0:
            mu = mu_ref
        else:
            mu = _mu_sutherland_numba(Ti, mu_ref)
        mu = max(mu, 1e-12)
        k_th = max(_k_powerlaw_numba(Ti, k_ref), 1e-12)
        cp = max(_cp_powerlaw_numba(Ti, cp_ref), 1e-9)

        Re = rho[i] * abs(u[i]) * diameter / mu
        pr = cp * mu / k_th if cp > 0.0 else pr_const
        Nu_turb = 0.023 * (Re ** 0.8) * (pr ** 0.4)
        Nu_lam = _NU_LAMINAR
        if Re <= 2300.0:
            Nu = Nu_lam
        elif Re >= 2300.0 + _SMOOTH_RE_SPAN:
            Nu = Nu_turb
        else:
            blend = (Re - 2300.0) / _SMOOTH_RE_SPAN
            Nu = Nu_lam * (1.0 - blend) + Nu_turb * blend
        h = Nu * k_th / diameter
        if h < h_min:
            h = h_min
        if h > h_max:
            h = h_max
        out[i] = h
    return out


def validate_wall_thermal_config(cfg: WallThermalConfig, label: str = "wall_thermal") -> None:
    if not cfg.enabled:
        return
    if cfg.m_wall_kg <= 0.0:
        raise ValueError(f"{label}.m_wall_kg must be positive")
    if cfg.cp_wall_j_per_kgk <= 0.0:
        raise ValueError(f"{label}.cp_wall_j_per_kgk must be positive")
    if cfg.h_w_per_m2k <= 0.0:
        raise ValueError(f"{label}.h_w_per_m2k must be positive")
    if cfg.h_model not in ("constant", "dittus_boelter"):
        raise ValueError(f"{label}.h_model must be 'constant' or 'dittus_boelter'")
    if cfg.h_mult < 0.0:
        raise ValueError(f"{label}.h_mult must be non-negative")
    if cfg.h_min < 0.0:
        raise ValueError(f"{label}.h_min must be non-negative")
    if cfg.h_max <= 0.0:
        raise ValueError(f"{label}.h_max must be positive")
    if cfg.h_max < cfg.h_min:
        raise ValueError(f"{label}.h_max must be >= h_min")
    if cfg.mu_model not in ("constant", "sutherland"):
        raise ValueError(f"{label}.mu_model must be 'constant' or 'sutherland'")
    if cfg.mu_const <= 0.0:
        raise ValueError(f"{label}.mu_const must be positive")
    if cfg.k_th_const <= 0.0:
        raise ValueError(f"{label}.k_th_const must be positive")
    if cfg.pr_const <= 0.0:
        raise ValueError(f"{label}.pr_const must be positive")
    if cfg.area_m2 <= 0.0:
        raise ValueError(f"{label}.area_m2 must be positive")
    if cfg.twall_min_k <= 0.0:
        raise ValueError(f"{label}.twall_min_k must be positive")
    if cfg.twall_max_k <= cfg.twall_min_k:
        raise ValueError(f"{label}.twall_max_k must exceed twall_min_k")


def clamp_wall_temperature(twall_k: float, cfg: WallThermalConfig) -> float:
    return min(max(twall_k, cfg.twall_min_k), cfg.twall_max_k)


def init_wall_temperature(cfg: WallThermalConfig) -> float:
    return clamp_wall_temperature(cfg.twall_init_k, cfg)


def _mu_from_model(T_gas: float, cfg: WallThermalConfig) -> float:
    if cfg.mu_model == "constant":
        return cfg.mu_const
    T = max(T_gas, 1e-9)
    T_ref = 273.15
    S = 110.4
    return cfg.mu_const * (T / T_ref) ** 1.5 * (T_ref + S) / (T + S)


def _thermal_properties(T: np.ndarray, cfg: WallThermalConfig, cp_ref: float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    T_arr = np.asarray(T, dtype=float)
    if cfg.mu_model == "constant":
        mu = np.full_like(T_arr, cfg.mu_const, dtype=float)
    else:
        T_safe = np.maximum(T_arr, 1e-6)
        T_ref = 273.15
        mu = cfg.mu_const * (T_safe / T_ref) ** 1.5 * (T_ref + _SUTHERLAND_S) / (T_safe + _SUTHERLAND_S)
    k_th = cfg.k_th_const * (np.maximum(T_arr, 1e-6) / _T_REF) ** 0.76
    cp = cp_ref * (np.maximum(T_arr, 1e-6) / _T_REF) ** 0.03
    mu = np.maximum(mu, 1e-12)
    k_th = np.maximum(k_th, 1e-12)
    cp = np.maximum(cp, 1e-9)
    return mu, k_th, cp


def _dittus_boelter_h_array(
    T: np.ndarray,
    rho: np.ndarray,
    u: np.ndarray,
    diameter_m: float,
    cfg: WallThermalConfig,
    cp_ref: float,
) -> np.ndarray:
    if diameter_m is None or diameter_m <= 0.0:
        return np.full_like(T, cfg.h_w_per_m2k, dtype=float)
    mu_model_flag = 0 if cfg.mu_model == "constant" else 1
    if _NUMBA_AVAILABLE:
        return _dittus_boelter_h_array_numba(
            T=np.asarray(T, dtype=np.float64),
            rho=np.asarray(rho, dtype=np.float64),
            u=np.asarray(u, dtype=np.float64),
            diameter_m=float(diameter_m),
            mu_ref=float(cfg.mu_const),
            k_ref=float(cfg.k_th_const),
            cp_ref=float(cp_ref),
            pr_const=float(cfg.pr_const),
            mu_model_flag=int(mu_model_flag),
            h_min=float(cfg.h_min),
            h_max=float(cfg.h_max),
        )

    mu, k_th, cp = _thermal_properties(T, cfg, cp_ref)
    diameter = max(float(diameter_m), 1e-9)
    Re = rho * np.abs(u) * diameter / np.maximum(mu, 1e-12)
    pr = cp * mu / np.maximum(k_th, 1e-12)
    Nu_turb = 0.023 * (Re ** 0.8) * (pr ** 0.4)
    Nu_lam = _NU_LAMINAR
    blend = np.clip((Re - 2300.0) / _SMOOTH_RE_SPAN, 0.0, 1.0)
    Nu = Nu_lam * (1.0 - blend) + Nu_turb * blend
    h = Nu * k_th / diameter
    h = np.clip(h, cfg.h_min, cfg.h_max)
    return h


def _h_from_model(
    cfg: WallThermalConfig,
    T_gas: float,
    rho: float | None,
    u: float | None,
    diameter_m: float | None,
    cp: float | None,
) -> float:
    if cfg.h_model == "constant":
        return cfg.h_w_per_m2k
    if rho is None or u is None or diameter_m is None or diameter_m <= 0.0:
        return cfg.h_w_per_m2k
    mu = _mu_from_model(T_gas, cfg)
    Re = rho * abs(u) * diameter_m / max(mu, 1e-12)
    if Re <= 2300.0:
        return cfg.h_min
    pr = cfg.pr_const
    if cp is not None and cp > 0.0:
        pr = cp * mu / max(cfg.k_th_const, 1e-12)
    Nu = 0.023 * (Re ** 0.8) * (pr ** 0.4)
    return Nu * cfg.k_th_const / max(diameter_m, 1e-12)


def wall_thermal_step(
    twall_k: float,
    T_gas: float,
    dt: float,
    cfg: WallThermalConfig,
    rho: float | None = None,
    u: float | None = None,
    diameter_m: float | None = None,
    cp: float | None = None,
) -> tuple[float, float]:
    if not cfg.enabled or dt <= 0.0:
        return twall_k, 0.0

    h = _h_from_model(cfg, T_gas, rho, u, diameter_m, cp)
    h = max(h * cfg.h_mult, 0.0)
    h = min(max(h, cfg.h_min), cfg.h_max)
    hA = h * cfg.area_m2
    denom = cfg.m_wall_kg * cfg.cp_wall_j_per_kgk
    if hA <= 0.0:
        return twall_k, 0.0
    if denom <= 0.0:
        raise ValueError("wall_thermal m_wall_kg and cp_wall_j_per_kgk must be positive")

    if not math.isfinite(twall_k) or not math.isfinite(T_gas):
        raise ValueError("wall_thermal requires finite temperatures")

    T_gas = max(T_gas, 1e-9)
    qdot = hA * (T_gas - twall_k)
    twall_new = twall_k + qdot * dt / denom
    twall_new = clamp_wall_temperature(twall_new, cfg)
    return twall_new, qdot
