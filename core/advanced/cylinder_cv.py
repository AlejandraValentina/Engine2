from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class HeatTransferConfig:
    enabled: bool = False
    model: str = "constant_h"
    h_const: float = 200.0
    wall_temp_K: float = 450.0
    c_woschni: float = 2.28
    clamp_qdot: float = 2e6


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
    heat_transfer: HeatTransferConfig = field(default_factory=HeatTransferConfig)

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
        A_wet: float | None = None,
    ) -> None:
        m_total_dot = mdot_in - mdot_out
        m_fresh_dot = Ydot_in - Ydot_out

        u_int = self.gas_constant * self.T / (self.gamma - 1.0)
        e_tot = self.m_total * u_int
        Qdot_ht = 0.0
        if self.heat_transfer.enabled:
            if A_wet is None or A_wet <= 0.0:
                raise ValueError("A_wet must be positive when heat transfer is enabled")
            if self.heat_transfer.model == "constant_h":
                h = self.heat_transfer.h_const
            elif self.heat_transfer.model == "woschni_simplified":
                v_ref = abs(dVdt) / max(self.V, 1e-12)
                h = (
                    self.heat_transfer.c_woschni
                    * (max(self.p, 1e-6) ** 0.8)
                    * (max(self.T, 1e-9) ** -0.55)
                    * (max(v_ref, 0.0) ** 0.8)
                )
            else:
                raise ValueError(f"Unknown heat transfer model '{self.heat_transfer.model}'")
            Qdot_ht = h * A_wet * (self.T - self.heat_transfer.wall_temp_K)
            if not math.isfinite(Qdot_ht):
                raise ValueError("Heat transfer produced non-finite Qdot_ht")
            if abs(Qdot_ht) > self.heat_transfer.clamp_qdot:
                raise ValueError("Heat transfer exceeds clamp_qdot")

        e_dot = (Qdot_net - Qdot_ht) - self.p * dVdt + (Hdot_in - Hdot_out)

        m_total = max(self.m_total + m_total_dot * dt, 1e-9)
        m_fresh = self.m_fresh + m_fresh_dot * dt
        m_fresh = min(max(m_fresh, 0.0), m_total)
        self.m_total = m_total
        self.m_fresh = m_fresh
        e_tot = max(e_tot + e_dot * dt, 1e-9)
        self.T = max(e_tot / (self.m_total * self.gas_constant / (self.gamma - 1.0)), 1e-6)
        self.p = self.m_total * self.gas_constant * self.T / max(self.V, 1e-12)

    def apply_combustion(self, dt: float, m_fuel_inj: float, wiebe_fraction: float) -> float:
        m_fuel_burn = min(m_fuel_inj * wiebe_fraction, self.m_fresh / max(self.afr_stoich, 1e-9))
        m_air_consumed = m_fuel_burn * self.afr_stoich
        self.m_fresh = min(max(self.m_fresh - m_air_consumed, 0.0), self.m_total)
        return m_fuel_burn * self.lhv * self.eta_comb / max(dt, 1e-9)


def slider_crank_volume(theta: float, bore: float, stroke: float, conrod: float, clearance: float) -> Tuple[float, float]:
    if conrod <= 0.0:
        raise ValueError("conrod length must be positive")
    r = stroke / 2.0
    l = conrod
    area = math.pi * (bore * 0.5) ** 2
    sin_theta = math.sin(theta)
    cos_theta = math.cos(theta)
    ratio = r / l
    root = max(1.0 - (sin_theta**2) * (ratio**2), 1e-12)
    sqrt_root = math.sqrt(root)
    term = 1.0 - cos_theta + ratio * (1.0 - sqrt_root)
    V = clearance + area * r * term
    dVdtheta = area * r * (sin_theta + ratio * (sin_theta * cos_theta) / sqrt_root)
    return V, dVdtheta
