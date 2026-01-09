from __future__ import annotations

import math
from dataclasses import dataclass
import logging
from typing import Optional, Tuple

import numpy as np

from core.advanced.nozzle import nozzle_mass_flow
from core.advanced.state import Primitive1D, primitive_to_conserved


@dataclass
class ValveTiming:
    open_start_deg: float
    open_end_deg: float
    max_lift_m: float
    seat_diameter_m: float
    cd: float
    n_valves: int = 1

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
        area = math.pi * self.seat_diameter_m * lift * max(self.n_valves, 1)
        return self.cd * max(area, 0.0)


def boundary_flux_from_nozzle(
    p0: float,
    T0: float,
    Y0: float,
    p_down: float,
    *,
    valve: ValveTiming,
    angle_deg: float,
    gamma: float,
    gas_constant: float,
    cp: float,
    p0_down: Optional[float] = None,
    T0_down: Optional[float] = None,
    Y0_down: Optional[float] = None,
) -> Tuple[float, float, float, float]:
    area_eff = valve.area_eff(angle_deg)
    mdot, Hdot, Ydot = nozzle_mass_flow(
        p0,
        T0,
        p_down,
        area_eff,
        gamma,
        gas_constant,
        cp,
        Y0,
        p0_down=p0_down,
        T0_down=T0_down,
        Y0_down=Y0_down,
    )
    return mdot, Hdot, Ydot, area_eff


def ghost_state_from_nozzle(
    p0: float,
    T0: float,
    Y0: float,
    mdot: float,
    area_face: float,
    gamma: float,
    gas_constant: float,
) -> np.ndarray:
    """Build a ghost state from upstream totals (Phase-1 approximation)."""
    if p0 < 1e3 or T0 < 50.0:
        raise ValueError(f"Invalid ghost totals (p0={p0:.3e}, T0={T0:.3e})")
    rho = max(p0 / (gas_constant * T0), 1e-9)
    u = mdot / max(rho * area_face, 1e-9)
    a = math.sqrt(max(gamma * gas_constant * T0, 1e-12))
    u_cap = 5.0 * a
    if abs(u) > u_cap:
        global _GHOST_VELOCITY_CAP_COUNT
        _GHOST_VELOCITY_CAP_COUNT += 1
        logger.error(
            "Ghost velocity cap applied: u=%.3e cap=%.3e count=%d",
            float(u),
            float(u_cap),
            _GHOST_VELOCITY_CAP_COUNT,
        )
        if _GHOST_VELOCITY_CAP_COUNT > _GHOST_VELOCITY_CAP_LIMIT:
            raise ValueError("Ghost velocity cap limit exceeded")
        u = float(np.clip(u, -u_cap, u_cap))
    prim = Primitive1D(rho=rho, u=u, p=p0, T=T0, Y=Y0)
    cons = primitive_to_conserved(prim, gamma, gas_constant)
    return np.array([cons.rho, cons.rhou, cons.rhoE, cons.rhoY], dtype=float)
logger = logging.getLogger(__name__)
_GHOST_VELOCITY_CAP_COUNT = 0
_GHOST_VELOCITY_CAP_LIMIT = 20


def reset_ghost_counters() -> None:
    global _GHOST_VELOCITY_CAP_COUNT
    _GHOST_VELOCITY_CAP_COUNT = 0
