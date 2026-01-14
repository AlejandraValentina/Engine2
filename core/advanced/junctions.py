from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Tuple

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
