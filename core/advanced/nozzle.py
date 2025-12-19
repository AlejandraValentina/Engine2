from __future__ import annotations

import math
from typing import Tuple


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
) -> Tuple[float, float, float]:
    """Return (mdot, Hdot, Ydot) with positive flow from upstream -> downstream."""

    if area_eff <= 0.0 or p0 <= 0.0 or T0 <= 0.0:
        raise ValueError("Invalid nozzle inputs (area_eff, p0, T0 must be positive)")

    def _mdot_mag(p_up: float, T_up: float, p_static: float) -> float:
        pr = max(min(p_static / p_up, 1.0), 0.0)
        crit = (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
        choked = pr <= crit
        if choked:
            flow_coeff = math.sqrt(gamma / gas_constant) * (2.0 / (gamma + 1.0)) ** (
                (gamma + 1.0) / (2.0 * (gamma - 1.0))
            )
            return area_eff * p_up / math.sqrt(T_up) * flow_coeff
        term = pr ** (2.0 / gamma) - pr ** ((gamma + 1.0) / gamma)
        term = max(term, 0.0)
        flow_coeff = math.sqrt(2.0 * gamma / (gas_constant * (gamma - 1.0)) * term)
        return area_eff * p_up / math.sqrt(T_up) * flow_coeff

    if p_down <= p0:
        mdot_mag = _mdot_mag(p0, T0, p_down)
        mdot = mdot_mag
        Hdot = mdot * cp * T0
        Ydot = mdot * Y0
    else:
        p0_rev = p0_down if p0_down is not None else p_down
        T0_rev = T0_down if T0_down is not None else T0
        Y0_rev = Y0_down if Y0_down is not None else Y0
        mdot_mag = _mdot_mag(p0_rev, T0_rev, p0)
        mdot = -mdot_mag
        Hdot = mdot * cp * T0_rev
        Ydot = mdot * Y0_rev

    return float(mdot), float(Hdot), float(Ydot)
