from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass
class CombustionConfig:
    enabled: bool = False
    afr_stoich: float = 14.7
    fuel_lhv: float = 43e6
    eta_comb_base: float = 0.95
    eta_comb_min: float = 0.70
    eta_comb_residual_k: float = 0.0
    wiebe_a: float = 5.0
    wiebe_m: float = 2.0
    start_angle_deg_atdc: float = -10.0
    duration_deg: float = 60.0
    duration_residual_k: float = 0.0
    clamp_X_res: Tuple[float, float] = (0.0, 0.8)


def crank_deg_per_sec(rpm: float) -> float:
    return 6.0 * rpm


def wiebe_xb(
    theta_deg: float,
    start_deg: float,
    duration_deg: float,
    wiebe_a: float,
    wiebe_m: float,
) -> float:
    if duration_deg <= 0.0:
        return 0.0
    phi = (theta_deg - start_deg) / duration_deg
    if phi <= 0.0:
        return 0.0
    if phi >= 1.0:
        return 1.0
    a = max(wiebe_a, 1e-9)
    m = max(wiebe_m, 0.0)
    denom = 1.0 - math.exp(-a)
    if denom <= 0.0:
        return 0.0
    return (1.0 - math.exp(-a * phi ** (m + 1.0))) / denom


def wiebe_dxb_dtheta(
    theta_deg: float,
    start_deg: float,
    duration_deg: float,
    wiebe_a: float,
    wiebe_m: float,
) -> float:
    if duration_deg <= 0.0:
        return 0.0
    phi = (theta_deg - start_deg) / duration_deg
    if phi <= 0.0 or phi >= 1.0:
        return 0.0
    a = max(wiebe_a, 1e-9)
    m = max(wiebe_m, 0.0)
    denom = 1.0 - math.exp(-a)
    if denom <= 0.0:
        return 0.0
    exp_term = math.exp(-a * phi ** (m + 1.0))
    dxb_dphi = exp_term * a * (m + 1.0) * (phi ** m) / denom
    return dxb_dphi / duration_deg


def combustion_qdot(
    theta_deg: float,
    rpm: float,
    m_fresh: float,
    m_total: float,
    cfg: CombustionConfig,
    tdc_firing_deg: float = 360.0,
) -> float:
    if not cfg.enabled:
        return 0.0

    m_total_safe = max(m_total, 1e-12)
    Y_fresh = max(min(m_fresh / m_total_safe, 1.0), 0.0)
    X_res = 1.0 - Y_fresh
    X_res = min(max(X_res, cfg.clamp_X_res[0]), cfg.clamp_X_res[1])

    dur_eff = cfg.duration_deg * (1.0 + cfg.duration_residual_k * X_res)
    if dur_eff <= 0.0:
        return 0.0

    eta_eff = cfg.eta_comb_base * (1.0 - cfg.eta_comb_residual_k * X_res)
    eta_eff = min(max(eta_eff, cfg.eta_comb_min), 1.0)

    m_air = max(m_fresh, 0.0)
    m_fuel = m_air / max(cfg.afr_stoich, 1e-9)
    Q_total = m_fuel * cfg.fuel_lhv * eta_eff

    burn_start_abs = tdc_firing_deg + cfg.start_angle_deg_atdc
    dxb_dtheta = wiebe_dxb_dtheta(
        theta_deg,
        burn_start_abs,
        dur_eff,
        cfg.wiebe_a,
        cfg.wiebe_m,
    )
    dxb_dt = dxb_dtheta * crank_deg_per_sec(rpm)
    Qdot = Q_total * dxb_dt
    if not math.isfinite(Qdot) or Qdot < 0.0:
        raise ValueError(f"Non-physical Qdot computed: {Qdot}")
    return Qdot
