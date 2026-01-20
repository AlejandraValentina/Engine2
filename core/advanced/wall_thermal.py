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


def wall_thermal_step(
    twall_k: float,
    T_gas: float,
    dt: float,
    cfg: WallThermalConfig,
) -> tuple[float, float]:
    if not cfg.enabled or dt <= 0.0:
        return twall_k, 0.0

    hA = cfg.h_w_per_m2k * cfg.area_m2
    denom = cfg.m_wall_kg * cfg.cp_wall_j_per_kgk
    if hA <= 0.0:
        raise ValueError("wall_thermal h_w_per_m2k and area_m2 must be positive")
    if denom <= 0.0:
        raise ValueError("wall_thermal m_wall_kg and cp_wall_j_per_kgk must be positive")

    if not math.isfinite(twall_k) or not math.isfinite(T_gas):
        raise ValueError("wall_thermal requires finite temperatures")

    T_gas = max(T_gas, 1e-9)
    qdot = hA * (T_gas - twall_k)
    twall_new = twall_k + qdot * dt / denom
    twall_new = clamp_wall_temperature(twall_new, cfg)
    return twall_new, qdot
