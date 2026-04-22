from __future__ import annotations

import math
from typing import Tuple

from core.thermo import thermally_perfect_cp, thermally_perfect_gamma

_DP_HYST_PA = 100.0


def mdot_mag_from_totals(
    p0_up: float,
    T0_up: float,
    p_static_down: float,
    area_eff: float,
    gamma: float,
    gas_constant: float,
) -> float:
    if p0_up <= 0.0 or T0_up <= 0.0:
        raise ValueError("Invalid nozzle inputs (p0_up, T0_up must be positive)")
    if area_eff <= 0.0:
        return 0.0
    pr = max(min(p_static_down / p0_up, 1.0), 0.0)
    crit = (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
    choked = pr <= crit
    if choked:
        flow_coeff = math.sqrt(gamma / gas_constant) * (2.0 / (gamma + 1.0)) ** (
            (gamma + 1.0) / (2.0 * (gamma - 1.0))
        )
        return area_eff * p0_up / math.sqrt(T0_up) * flow_coeff
    term = pr ** (2.0 / gamma) - pr ** ((gamma + 1.0) / gamma)
    term = max(term, 0.0)
    flow_coeff = math.sqrt(2.0 * gamma / (gas_constant * (gamma - 1.0)) * term)
    return area_eff * p0_up / math.sqrt(T0_up) * flow_coeff


def _direction_from_totals(
    p0: float, p0_down: float | None, p_down: float
) -> bool:
    if p0_down is None or not math.isfinite(p0_down) or p0_down <= 0.0:
        return p_down <= p0
    if p0 > p0_down + _DP_HYST_PA:
        return True
    if p0_down > p0 + _DP_HYST_PA:
        return False
    return p_down <= p0


def nozzle_mass_flow(
    p0: float,
    T0: float,
    p_down: float,
    area_eff: float,
    gamma: float,
    gas_constant: float,
    cp: float,
    Y0: float,
    p0_down: float | None = None,
    T0_down: float | None = None,
    Y0_down: float | None = None,
    cp_model: str = "constant",
) -> Tuple[float, float, float]:
    """Return (mdot, Hdot, Ydot) with positive flow from upstream -> downstream."""

    if area_eff < 0.0:
        raise ValueError("Invalid nozzle inputs (area_eff must be non-negative)")
    if area_eff == 0.0:
        return 0.0, 0.0, 0.0
    if p0 <= 0.0 or T0 <= 0.0:
        raise ValueError("Invalid nozzle inputs (p0, T0 must be positive)")

    forward = _direction_from_totals(p0, p0_down, p_down)
    if cp_model == "nasa7":
        gamma_up = thermally_perfect_gamma(T0, Y0, gas_constant)
        cp_up = thermally_perfect_cp(T0, Y0, gas_constant)
    else:
        gamma_up = gamma
        cp_up = cp

    if forward:
        mdot_mag = mdot_mag_from_totals(p0, T0, p_down, area_eff, gamma_up, gas_constant)
        mdot = mdot_mag
        Hdot = mdot * cp_up * T0
        Ydot = mdot * Y0
    else:
        p0_rev = p0_down if p0_down is not None else p_down
        T0_rev = T0_down if T0_down is not None else T0
        Y0_rev = Y0_down if Y0_down is not None else Y0
        if cp_model == "nasa7":
            gamma_rev = thermally_perfect_gamma(T0_rev, Y0_rev, gas_constant)
            cp_rev = thermally_perfect_cp(T0_rev, Y0_rev, gas_constant)
        else:
            gamma_rev = gamma
            cp_rev = cp
        mdot_mag = mdot_mag_from_totals(p0_rev, T0_rev, p0, area_eff, gamma_rev, gas_constant)
        mdot = -mdot_mag
        Hdot = mdot * cp_rev * T0_rev
        Ydot = mdot * Y0_rev

    return float(mdot), float(Hdot), float(Ydot)
