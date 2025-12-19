from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from core.advanced.nozzle import nozzle_mass_flow
from core.advanced.state import Primitive1D, primitive_to_conserved


@dataclass
class ValveTiming:
    open_start_deg: float
    open_end_deg: float
    max_lift_m: float
    seat_diameter_m: float
    cd: float

    def area_eff(self, angle_deg: float) -> float:
        angle = angle_deg % 720.0
        start = self.open_start_deg % 720.0
        end = self.open_end_deg % 720.0

        if start <= end:
            if not (start <= angle <= end):
                return 0.0
            phase = (angle - start) / max(end - start, 1e-6)
        else:
            if not (angle >= start or angle <= end):
                return 0.0
            span = (720.0 - start) + end
            phase = ((angle - start) % 720.0) / max(span, 1e-6)

        lift = self.max_lift_m * (math.sin(math.pi * phase) ** 2)
        area = math.pi * self.seat_diameter_m * lift
        return self.cd * max(area, 0.0)


def boundary_flux_from_nozzle(
    p0: float,
    T0: float,
    Y0: float,
    p_down: float,
    area: float,
    gamma: float,
    gas_constant: float,
    cd: float,
    cp: float,
) -> Tuple[float, float, float, float]:
    mdot, Hdot, Ydot = nozzle_mass_flow(p0, T0, p_down, area, gamma, gas_constant, cd, cp, Y0)
    return mdot, Hdot, Ydot, area


def ghost_state_from_nozzle(
    p0: float,
    T0: float,
    Y0: float,
    mdot: float,
    area: float,
    gamma: float,
    gas_constant: float,
) -> np.ndarray:
    rho = max(p0 / (gas_constant * T0), 1e-9)
    u = mdot / max(rho * area, 1e-9)
    prim = Primitive1D(rho=rho, u=u, p=p0, T=T0, Y=Y0)
    cons = primitive_to_conserved(prim, gamma, gas_constant)
    return np.array([cons.rho, cons.rhou, cons.rhoE, cons.rhoY], dtype=float)
