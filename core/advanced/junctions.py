from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Tuple

from core.advanced.wall_thermal import init_wall_temperature, validate_wall_thermal_config, wall_thermal_step
from core.engine_components import WallThermalConfig
from core.advanced.nozzle import mdot_mag_from_totals


@dataclass
class JunctionFlow:
    mdot: float
    p0: float
    T0: float
    Y0: float


@dataclass
class JunctionLegConfig:
    k_loss: float = 0.0
    use_geometry_K: bool = False
    angle_deg: float = 0.0
    area_ratio: float = 1.0
    quality: float = 0.5

    def effective_k_loss(self) -> float:
        if self.use_geometry_K and self.k_loss <= 0.0:
            return estimate_K_from_geometry(self.angle_deg, self.area_ratio, self.quality)
        return self.k_loss

    def to_dict(self) -> dict:
        return {
            "k_loss": self.k_loss,
            "use_geometry_K": self.use_geometry_K,
            "angle_deg": self.angle_deg,
            "area_ratio": self.area_ratio,
            "quality": self.quality,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JunctionLegConfig":
        return cls(
            k_loss=float(data.get("k_loss", 0.0)),
            use_geometry_K=bool(data.get("use_geometry_K", False)),
            angle_deg=float(data.get("angle_deg", 0.0)),
            area_ratio=float(data.get("area_ratio", 1.0)),
            quality=float(data.get("quality", 0.5)),
        )


@dataclass
class JunctionCapacitanceConfig:
    enabled: bool = False
    volume_m3: float = 0.0
    p_min_Pa: float = 1000.0
    T_min_K: float = 50.0
    under_relax_alpha: float = 1.0

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "volume_m3": self.volume_m3,
            "p_min_Pa": self.p_min_Pa,
            "T_min_K": self.T_min_K,
            "under_relax_alpha": self.under_relax_alpha,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JunctionCapacitanceConfig":
        return cls(
            enabled=bool(data.get("enabled", False)),
            volume_m3=float(data.get("volume_m3", 0.0)),
            p_min_Pa=float(data.get("p_min_Pa", 1000.0)),
            T_min_K=float(data.get("T_min_K", 50.0)),
            under_relax_alpha=float(data.get("under_relax_alpha", 1.0)),
        )


class JunctionCapacitance:
    """0D reservoir node for multi-leg junctions (optional)."""

    def __init__(
        self,
        config: JunctionCapacitanceConfig,
        gamma: float,
        gas_constant: float,
        cp: float,
        p_init: float = 101325.0,
        T_init: float = 300.0,
        Y_init: float = 0.0,
        wall_thermal: WallThermalConfig | None = None,
    ) -> None:
        if config.enabled and config.volume_m3 <= 0.0:
            raise ValueError("volume_m3 must be positive when junction capacitance is enabled")
        self.config = config
        self.gamma = gamma
        self.gas_constant = gas_constant
        self.cp = cp
        self.volume_m3 = max(config.volume_m3, 1e-12)
        self.wall_thermal = wall_thermal or WallThermalConfig()
        validate_wall_thermal_config(self.wall_thermal, "junction_capacitance.wall_thermal")

        Y_init_clamped = min(max(Y_init, 0.0), 1.0)
        self.m_total = max(p_init * self.volume_m3 / (gas_constant * max(T_init, 1e-6)), 1e-9)
        cv = self._cv()
        self.E_total = self.m_total * cv * max(T_init, 1e-6)
        self.mY = self.m_total * Y_init_clamped
        self.p = p_init
        self.T = T_init
        self.Y = Y_init_clamped
        self.twall = init_wall_temperature(self.wall_thermal)

    def _cv(self) -> float:
        cv = self.cp - self.gas_constant
        if cv <= 0.0:
            raise ValueError("Invalid cp/gas_constant for junction capacitance")
        return cv

    def totals(self) -> Tuple[float, float, float]:
        return float(self.p), float(self.T), float(self.Y)

    def update(
        self,
        dt: float,
        inflows: Iterable[JunctionFlow],
        outflows: Iterable[JunctionFlow],
    ) -> Tuple[float, float, float]:
        if not self.config.enabled:
            return self.totals()

        dm = 0.0
        dE = 0.0
        dMY = 0.0
        for flow in inflows:
            dm += flow.mdot
            dE += flow.mdot * self.cp * flow.T0
            dMY += flow.mdot * flow.Y0
        for flow in outflows:
            dm -= flow.mdot
            dE -= flow.mdot * self.cp * flow.T0
            dMY -= flow.mdot * flow.Y0

        qdot_ht = 0.0
        if self.wall_thermal.enabled:
            self.twall, qdot_ht = wall_thermal_step(self.twall, self.T, dt, self.wall_thermal)

        target_m = self.m_total + dm * dt
        target_E = self.E_total + dE * dt - qdot_ht * dt
        target_mY = self.mY + dMY * dt

        alpha = min(max(self.config.under_relax_alpha, 0.0), 1.0)
        self.m_total = self.m_total + alpha * (target_m - self.m_total)
        self.E_total = self.E_total + alpha * (target_E - self.E_total)
        self.mY = self.mY + alpha * (target_mY - self.mY)

        self.m_total = max(self.m_total, 1e-9)
        Y_new = self.mY / max(self.m_total, 1e-12)
        Y_new = min(max(Y_new, 0.0), 1.0)
        self.mY = self.m_total * Y_new
        self.Y = Y_new

        cv = self._cv()
        T_new = self.E_total / max(self.m_total * cv, 1e-12)
        if T_new < self.config.T_min_K:
            T_new = self.config.T_min_K
            self.E_total = self.m_total * cv * T_new
        rho = self.m_total / self.volume_m3
        p_new = rho * self.gas_constant * T_new
        if p_new < self.config.p_min_Pa:
            p_new = self.config.p_min_Pa
            T_new = max(p_new * self.volume_m3 / (self.m_total * self.gas_constant), self.config.T_min_K)
            self.E_total = self.m_total * cv * T_new

        self.p = p_new
        self.T = T_new
        return self.totals()


def estimate_K_from_geometry(angle_deg: float, area_ratio: float, quality: float = 0.5) -> float:
    """Estimate a junction loss seed from geometry (angle + area mismatch)."""
    angle = max(min(angle_deg, 180.0), 0.0)
    area_ratio_safe = max(area_ratio, 1e-3)
    quality_clamped = min(max(quality, 0.0), 1.0)
    angle_term = math.radians(angle) / math.pi
    area_term = (area_ratio_safe - 1.0) ** 2
    quality_term = 1.0 - 0.7 * quality_clamped
    return max((1.0 + area_term) * angle_term * quality_term, 0.0)


def mix_junction_totals(flows: Iterable[JunctionFlow], cp: float) -> Tuple[float, float, float]:
    flows_list = list(flows)
    if not flows_list:
        raise ValueError("At least one inflow is required")
    total_mdot = sum(flow.mdot for flow in flows_list)
    if total_mdot <= 0.0:
        raise ValueError("Total inflow must be positive")
    p0_mix = sum(flow.mdot * flow.p0 for flow in flows_list) / total_mdot
    h0_mix = sum(flow.mdot * cp * flow.T0 for flow in flows_list) / total_mdot
    T0_mix = h0_mix / max(cp, 1e-12)
    Y_mix = sum(flow.mdot * flow.Y0 for flow in flows_list) / total_mdot
    return float(p0_mix), float(T0_mix), float(Y_mix)


def apply_junction_loss(
    mdot0: float,
    p0_up: float,
    T0_up: float,
    Y0_up: float,
    p_down: float,
    area_eff: float,
    gamma: float,
    gas_constant: float,
    cp: float,
    loss_coeff: float = 0.0,
    rho_down: float | None = None,
    u_down: float | None = None,
    area_pipe_m2: float | None = None,
) -> Tuple[float, float, float]:
    if loss_coeff < 0.0:
        raise ValueError("loss_coeff must be non-negative")
    if area_eff <= 0.0:
        return 0.0, 0.0, 0.0
    if mdot0 == 0.0 or loss_coeff == 0.0:
        return mdot0, mdot0 * cp * T0_up, mdot0 * Y0_up
    if rho_down is None:
        raise ValueError("loss_coeff requires rho_down")
    if area_pipe_m2 is not None:
        if area_pipe_m2 <= 0.0:
            raise ValueError("area_pipe_m2 must be positive")
        v_face = abs(mdot0) / max(rho_down * area_pipe_m2, 1e-12)
    else:
        if u_down is None:
            raise ValueError("loss_coeff requires u_down when area_pipe_m2 is not provided")
        v_face = abs(u_down)
    dp_loss = 0.5 * loss_coeff * rho_down * v_face * v_face
    if not math.isfinite(dp_loss) or dp_loss < 0.0:
        raise ValueError("Invalid local loss pressure drop")
    p_eff = max(p_down + dp_loss, 1e-6)
    mdot_mag = mdot_mag_from_totals(p0_up, T0_up, p_eff, area_eff, gamma, gas_constant)
    mdot = math.copysign(mdot_mag, mdot0)
    return mdot, mdot * cp * T0_up, mdot * Y0_up


def junction_outflow_from_totals(
    p0_up: float,
    T0_up: float,
    Y0_up: float,
    p_down: float,
    area_eff: float,
    gamma: float,
    gas_constant: float,
    cp: float,
    loss_coeff: float = 0.0,
    rho_down: float | None = None,
    u_down: float | None = None,
    area_pipe_m2: float | None = None,
) -> Tuple[float, float, float]:
    mdot0 = mdot_mag_from_totals(p0_up, T0_up, p_down, area_eff, gamma, gas_constant)
    return apply_junction_loss(
        mdot0,
        p0_up,
        T0_up,
        Y0_up,
        p_down,
        area_eff,
        gamma,
        gas_constant,
        cp,
        loss_coeff=loss_coeff,
        rho_down=rho_down,
        u_down=u_down,
        area_pipe_m2=area_pipe_m2,
    )
