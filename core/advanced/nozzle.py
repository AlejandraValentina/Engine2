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
    cd: float,
    cp: float,
    Y0: float,
) -> Tuple[float, float, float]:
    """Return (mdot, Hdot, Ydot) with positive flow from upstream -> downstream."""

    if area_eff <= 0.0 or p0 <= 0.0 or T0 <= 0.0:
        return 0.0, 0.0, 0.0

    cd = max(cd, 0.0)
    pr = max(min(p_down / p0, 1.0), 0.0)
    crit = (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
    choked = pr <= crit

    if choked:
        flow_coeff = math.sqrt(gamma / gas_constant) * (2.0 / (gamma + 1.0)) ** (
            (gamma + 1.0) / (2.0 * (gamma - 1.0))
        )
        mdot = cd * area_eff * p0 / math.sqrt(T0) * flow_coeff
    else:
        term = pr ** (2.0 / gamma) - pr ** ((gamma + 1.0) / gamma)
        term = max(term, 0.0)
        flow_coeff = math.sqrt(2.0 * gamma / (gas_constant * (gamma - 1.0)) * term)
        mdot = cd * area_eff * p0 / math.sqrt(T0) * flow_coeff

    if p_down > p0:
        mdot = -mdot

    Hdot = mdot * cp * T0
    Ydot = mdot * Y0
    return float(mdot), float(Hdot), float(Ydot)
