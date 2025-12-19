from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass
class CylinderControlVolume:
    m_total: float
    m_fresh: float
    T: float
    p: float
    V: float
    gamma: float
    gas_constant: float
    afr_stoich: float = 14.7
    lhv: float = 44e6
    eta_comb: float = 0.5

    def update(
        self,
        dt: float,
        mdot_in: float,
        Hdot_in: float,
        Ydot_in: float,
        mdot_out: float,
        Hdot_out: float,
        Ydot_out: float,
        Qdot_net: float,
        dVdt: float,
    ) -> None:
        m_total_dot = mdot_in - mdot_out
        m_fresh_dot = Ydot_in - Ydot_out

        u_int = self.gas_constant * self.T / (self.gamma - 1.0)
        e_tot = self.m_total * u_int
        e_dot = Qdot_net - self.p * dVdt + (Hdot_in - Hdot_out)

        self.m_total = max(self.m_total + m_total_dot * dt, 1e-9)
        self.m_fresh = max(self.m_fresh + m_fresh_dot * dt, 0.0)
        e_tot = max(e_tot + e_dot * dt, 1e-9)
        self.T = max(e_tot / (self.m_total * self.gas_constant / (self.gamma - 1.0)), 1e-6)
        self.p = self.m_total * self.gas_constant * self.T / max(self.V, 1e-12)

    def apply_combustion(self, dt: float, m_fuel_inj: float, wiebe_fraction: float) -> float:
        m_fuel_burn = min(m_fuel_inj * wiebe_fraction, self.m_fresh / max(self.afr_stoich, 1e-9))
        m_air_consumed = m_fuel_burn * self.afr_stoich
        self.m_fresh = max(self.m_fresh - m_air_consumed, 0.0)
        return m_fuel_burn * self.lhv * self.eta_comb / max(dt, 1e-9)


def slider_crank_volume(theta: float, bore: float, stroke: float, conrod: float, clearance: float) -> Tuple[float, float]:
    r = stroke / 2.0
    l = conrod
    area = math.pi * (bore * 0.5) ** 2
    term = 1.0 - math.cos(theta) + (r / l) * (1.0 - math.sqrt(1.0 - (math.sin(theta) ** 2) * (r / l) ** 2))
    V = clearance + area * r * term
    dVdtheta = area * r * (math.sin(theta) + (r / l) * (math.sin(theta) * math.cos(theta)) / math.sqrt(1.0 - (math.sin(theta) ** 2) * (r / l) ** 2))
    return V, dVdtheta
