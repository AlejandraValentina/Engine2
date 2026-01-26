from __future__ import annotations

import math

from core.engine_components import WallThermalConfig


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
