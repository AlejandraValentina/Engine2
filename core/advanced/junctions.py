from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple

from core.advanced.coupling import ghost_state_from_nozzle
from core.advanced.nozzle import nozzle_mass_flow
from core.advanced.state import stagnation_from_static
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
    p_init_pa: float | None = None
    t_init_k: float | None = None
    y_init: float | None = None
    p_floor_pa: float = 20000.0
    t_floor_k: float = 200.0
    max_dt_s: float | None = None

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "volume_m3": self.volume_m3,
            "p_min_Pa": self.p_min_Pa,
            "T_min_K": self.T_min_K,
            "under_relax_alpha": self.under_relax_alpha,
            "p_init_pa": self.p_init_pa,
            "t_init_k": self.t_init_k,
            "y_init": self.y_init,
            "p_floor_pa": self.p_floor_pa,
            "t_floor_k": self.t_floor_k,
            "max_dt_s": self.max_dt_s,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JunctionCapacitanceConfig":
        p_init_pa = data.get("p_init_pa")
        if p_init_pa is None and "p_init_Pa" in data:
            p_init_pa = data.get("p_init_Pa")
        t_init_k = data.get("t_init_k")
        if t_init_k is None and "T_init_K" in data:
            t_init_k = data.get("T_init_K")
        y_init = data.get("y_init")
        if y_init is None and "Y_init" in data:
            y_init = data.get("Y_init")
        p_floor_pa = data.get("p_floor_pa")
        if p_floor_pa is None and "p_min_Pa" in data:
            p_floor_pa = data.get("p_min_Pa")
        t_floor_k = data.get("t_floor_k")
        if t_floor_k is None and "T_min_K" in data:
            t_floor_k = data.get("T_min_K")
        return cls(
            enabled=bool(data.get("enabled", False)),
            volume_m3=float(data.get("volume_m3", 0.0)),
            p_min_Pa=float(data.get("p_min_Pa", 1000.0)),
            T_min_K=float(data.get("T_min_K", 50.0)),
            under_relax_alpha=float(data.get("under_relax_alpha", 1.0)),
            p_init_pa=float(p_init_pa) if p_init_pa is not None else None,
            t_init_k=float(t_init_k) if t_init_k is not None else None,
            y_init=float(y_init) if y_init is not None else None,
            p_floor_pa=float(p_floor_pa) if p_floor_pa is not None else 20000.0,
            t_floor_k=float(t_floor_k) if t_floor_k is not None else 200.0,
            max_dt_s=float(data.get("max_dt_s")) if data.get("max_dt_s") is not None else None,
        )


@dataclass
class JunctionLossConfig:
    enabled: bool = False
    legs: Dict[str, float] = field(default_factory=dict)
    default_k: float = 0.0

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "legs": self.legs,
            "default_k": self.default_k,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "JunctionLossConfig":
        legs = data.get("legs", {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            legs={str(key): float(val) for key, val in legs.items()} if isinstance(legs, dict) else {},
            default_k=float(data.get("default_k", 0.0)),
        )

    def k_for_leg(self, leg_id: str) -> float:
        if not self.enabled:
            return 0.0
        return float(self.legs.get(leg_id, self.default_k))


@dataclass
class JunctionCapacitanceState:
    m_total: float
    E_total: float
    mY: float
    p: float
    T: float
    Y: float


def _junction_cv(cp: float, gas_constant: float) -> float:
    cv = cp - gas_constant
    if cv <= 0.0:
        raise ValueError("Invalid cp/gas_constant for junction capacitance")
    return cv


def _junction_floors(cfg: JunctionCapacitanceConfig) -> Tuple[float, float]:
    p_floor = cfg.p_floor_pa if cfg.p_floor_pa is not None else cfg.p_min_Pa
    t_floor = cfg.t_floor_k if cfg.t_floor_k is not None else cfg.T_min_K
    return float(p_floor), float(t_floor)


def _junction_min_mass(
    cfg: JunctionCapacitanceConfig, volume_m3: float, gas_constant: float
) -> float:
    _, t_floor = _junction_floors(cfg)
    t_floor = max(t_floor, 1e-6)
    p_floor, _ = _junction_floors(cfg)
    return max(1e-9, p_floor * volume_m3 / (gas_constant * t_floor))


def init_junction_capacitance_state(
    cfg: JunctionCapacitanceConfig,
    gas_constant: float,
    cp: float,
    gamma: float,
    *,
    p_amb: float,
    t_amb: float,
    y_default: float,
    p_init_override: float | None = None,
    t_init_override: float | None = None,
    y_init_override: float | None = None,
) -> JunctionCapacitanceState:
    _ = gamma
    p_floor, t_floor = _junction_floors(cfg)

    p_init = p_init_override
    if p_init is None:
        p_init = cfg.p_init_pa if cfg.p_init_pa is not None else p_amb
    t_init = t_init_override
    if t_init is None:
        t_init = cfg.t_init_k if cfg.t_init_k is not None else t_amb
    y_init = y_init_override
    if y_init is None:
        y_init = cfg.y_init if cfg.y_init is not None else y_default

    p_init = max(float(p_init), p_floor)
    t_init = max(float(t_init), t_floor)
    y_init = min(max(float(y_init), 0.0), 1.0)

    volume_m3 = max(cfg.volume_m3, 1e-12)
    cv = _junction_cv(cp, gas_constant)
    m_min = _junction_min_mass(cfg, volume_m3, gas_constant)

    m_total = max(p_init * volume_m3 / (gas_constant * max(t_init, 1e-6)), m_min)
    E_total = m_total * cv * max(t_init, 1e-6)
    mY = m_total * y_init

    return JunctionCapacitanceState(
        m_total=m_total,
        E_total=E_total,
        mY=mY,
        p=p_init,
        T=t_init,
        Y=y_init,
    )


def update_junction_capacitance_state(
    state: JunctionCapacitanceState,
    cfg: JunctionCapacitanceConfig,
    gas_constant: float,
    cp: float,
    volume_m3: float,
    dt: float,
    mdot_in: float,
    Hdot_in: float,
    Ydot_in: float,
    mdot_out: float,
    Hdot_out: float,
    Ydot_out: float,
) -> None:
    if not cfg.enabled or dt <= 0.0:
        return
    if cfg.max_dt_s is not None and cfg.max_dt_s > 0.0:
        dt = min(dt, cfg.max_dt_s)
    p_floor, t_floor = _junction_floors(cfg)
    cv = _junction_cv(cp, gas_constant)

    volume_m3 = max(volume_m3, 1e-12)
    m_min = _junction_min_mass(cfg, volume_m3, gas_constant)

    state.m_total = max(state.m_total + (mdot_in - mdot_out) * dt, m_min)
    state.E_total = max(state.E_total + (Hdot_in - Hdot_out) * dt, 1e-9)
    state.mY = state.mY + (Ydot_in - Ydot_out) * dt

    Y_new = state.mY / max(state.m_total, 1e-12)
    Y_new = min(max(Y_new, 0.0), 1.0)
    state.mY = state.m_total * Y_new

    T_new = state.E_total / max(state.m_total * cv, 1e-12)
    if T_new < t_floor:
        T_new = t_floor

    rho = state.m_total / volume_m3
    p_new = rho * gas_constant * T_new
    if p_new < p_floor:
        p_new = p_floor
        T_new = max(p_new * volume_m3 / (state.m_total * gas_constant), t_floor)

    alpha = max(min(cfg.under_relax_alpha, 1.0), 0.0)
    T_relaxed = state.T + alpha * (T_new - state.T)
    if T_relaxed < t_floor:
        T_relaxed = t_floor
    p_relaxed = rho * gas_constant * T_relaxed
    if p_relaxed < p_floor:
        p_relaxed = p_floor
        T_relaxed = max(p_relaxed * volume_m3 / (state.m_total * gas_constant), t_floor)
        p_relaxed = rho * gas_constant * T_relaxed

    state.T = T_relaxed
    state.p = p_relaxed
    state.Y = Y_new
    state.E_total = state.m_total * cv * state.T


def resolve_junction_leg_k_loss(
    leg_id: str,
    leg_cfg: Optional[JunctionLegConfig] = None,
    loss_cfg: Optional[JunctionLossConfig] = None,
) -> float:
    if loss_cfg is not None and loss_cfg.enabled:
        return loss_cfg.k_for_leg(leg_id)
    if leg_cfg is None:
        return 0.0
    return float(leg_cfg.effective_k_loss())


def build_junction_boundary_state(
    mdot: float,
    p0_pipe: float,
    T0_pipe: float,
    Y_pipe: float,
    p_j: float,
    T_j: float,
    Y_j: float,
    area_face: float,
    gamma: float,
    gas_constant: float,
    *,
    cp_model: str = "constant",
) -> "np.ndarray":
    if mdot < 0.0:
        ghost_p0 = p_j
        ghost_T0 = T_j
        ghost_Y0 = Y_j
    else:
        ghost_p0 = p0_pipe
        ghost_T0 = T0_pipe
        ghost_Y0 = Y_pipe
    return ghost_state_from_nozzle(
        ghost_p0,
        ghost_T0,
        ghost_Y0,
        mdot,
        max(area_face, 1e-9),
        gamma,
        gas_constant,
        phase="phase2",
        cp_model=cp_model,
    )


def junction_leg_flux(
    prim_pipe: Tuple[float, float, float, float, float],
    area_face: float,
    junction_state: JunctionCapacitanceState,
    gamma: float,
    gas_constant: float,
    cp: float,
    *,
    cp_model: str = "constant",
    loss_coeff: float | None = None,
    leg_id: str | None = None,
    leg_cfg: Optional[JunctionLegConfig] = None,
    loss_cfg: Optional[JunctionLossConfig] = None,
) -> Tuple[float, float, float, float, float]:
    rho_pipe, u_pipe, p_pipe, T_pipe, Y_pipe = prim_pipe
    p0_pipe, T0_pipe = stagnation_from_static(
        p_pipe,
        T_pipe,
        u_pipe,
        gamma,
        gas_constant,
        cp_model=cp_model,
        Y_fresh=Y_pipe,
    )

    mdot, Hdot, Ydot = nozzle_mass_flow(
        p0_pipe,
        T0_pipe,
        junction_state.p,
        area_face,
        gamma,
        gas_constant,
        cp,
        Y_pipe,
        p0_down=junction_state.p,
        T0_down=junction_state.T,
        Y0_down=junction_state.Y,
        cp_model=cp_model,
    )

    if loss_coeff is None:
        loss_coeff = resolve_junction_leg_k_loss(leg_id or "", leg_cfg=leg_cfg, loss_cfg=loss_cfg)
    if loss_coeff > 0.0 and mdot != 0.0:
        rho_face = max(rho_pipe, 1e-9)
        if mdot >= 0.0:
            mdot, Hdot, Ydot = apply_junction_loss(
                mdot,
                p0_pipe,
                T0_pipe,
                Y_pipe,
                junction_state.p,
                area_face,
                gamma,
                gas_constant,
                cp,
                loss_coeff=loss_coeff,
                rho_down=rho_face,
                area_pipe_m2=area_face,
            )
        else:
            mdot, Hdot, Ydot = apply_junction_loss(
                mdot,
                junction_state.p,
                junction_state.T,
                junction_state.Y,
                p_pipe,
                area_face,
                gamma,
                gas_constant,
                cp,
                loss_coeff=loss_coeff,
                rho_down=rho_face,
                area_pipe_m2=area_face,
            )

    return mdot, Hdot, Ydot, p0_pipe, T0_pipe


def junction_totals_from_flows(
    cfg: JunctionCapacitanceConfig,
    state: Optional[JunctionCapacitanceState],
    inflows: Iterable[JunctionFlow],
    outflows: Iterable[JunctionFlow],
    *,
    gas_constant: float,
    cp: float,
    gamma: float,
    dt: float,
    p_init: float,
    T_init: float,
    Y_init: float,
) -> Tuple[Optional[JunctionCapacitanceState], Tuple[float, float, float]]:
    if not cfg.enabled:
        return state, mix_junction_totals(inflows, cp)

    if state is None:
        state = init_junction_capacitance_state(
            cfg,
            gas_constant,
            cp,
            gamma,
            p_amb=p_init,
            t_amb=T_init,
            y_default=Y_init,
            p_init_override=p_init,
            t_init_override=T_init,
            y_init_override=Y_init,
        )

    mdot_in = 0.0
    Hdot_in = 0.0
    Ydot_in = 0.0
    mdot_out = 0.0
    Hdot_out = 0.0
    Ydot_out = 0.0
    for flow in inflows:
        mdot_in += flow.mdot
        Hdot_in += flow.mdot * cp * flow.T0
        Ydot_in += flow.mdot * flow.Y0
    for flow in outflows:
        mdot_out += flow.mdot
        Hdot_out += flow.mdot * cp * flow.T0
        Ydot_out += flow.mdot * flow.Y0

    update_junction_capacitance_state(
        state,
        cfg,
        gas_constant,
        cp,
        cfg.volume_m3,
        dt,
        mdot_in,
        Hdot_in,
        Ydot_in,
        mdot_out,
        Hdot_out,
        Ydot_out,
    )
    return state, (state.p, state.T, state.Y)
class JunctionCapacitance:
    """0D reservoir node for multi-leg junctions (optional)."""

    def __init__(
        self,
        config: JunctionCapacitanceConfig,
        gamma: float,
        gas_constant: float,
        cp: float,
        p_init: float | None = None,
        T_init: float | None = None,
        Y_init: float | None = None,
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

        p_init_val = p_init if p_init is not None else (config.p_init_pa or 101325.0)
        T_init_val = T_init if T_init is not None else (config.t_init_k or 300.0)
        Y_init_val = Y_init if Y_init is not None else (config.y_init if config.y_init is not None else 0.0)

        state = init_junction_capacitance_state(
            config,
            gas_constant,
            cp,
            gamma,
            p_amb=p_init_val,
            t_amb=T_init_val,
            y_default=Y_init_val,
            p_init_override=p_init_val,
            t_init_override=T_init_val,
            y_init_override=Y_init_val,
        )
        self.m_total = state.m_total
        self.E_total = state.E_total
        self.mY = state.mY
        self.p = state.p
        self.T = state.T
        self.Y = state.Y
        self.twall = init_wall_temperature(self.wall_thermal)

    def _cv(self) -> float:
        return _junction_cv(self.cp, self.gas_constant)

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

        mdot_in = 0.0
        Hdot_in = 0.0
        Ydot_in = 0.0
        mdot_out = 0.0
        Hdot_out = 0.0
        Ydot_out = 0.0
        for flow in inflows:
            mdot_in += flow.mdot
            Hdot_in += flow.mdot * self.cp * flow.T0
            Ydot_in += flow.mdot * flow.Y0
        for flow in outflows:
            mdot_out += flow.mdot
            Hdot_out += flow.mdot * self.cp * flow.T0
            Ydot_out += flow.mdot * flow.Y0

        qdot_ht = 0.0
        if self.wall_thermal.enabled:
            rho = self.p / (self.gas_constant * max(self.T, 1e-9))
            area = self.wall_thermal.area_m2
            mdot_through = 0.5 * (abs(mdot_in) + abs(mdot_out))
            u_eff = mdot_through / (rho * area) if area > 0.0 and rho > 0.0 else 0.0
            diameter = 4.0 * self.volume_m3 / area if area > 0.0 else None
            self.twall, qdot_ht = wall_thermal_step(
                self.twall,
                self.T,
                dt,
                self.wall_thermal,
                rho=rho,
                u=u_eff,
                diameter_m=diameter,
                cp=self.cp,
            )
            Hdot_out += qdot_ht

        state = JunctionCapacitanceState(
            m_total=self.m_total,
            E_total=self.E_total,
            mY=self.mY,
            p=self.p,
            T=self.T,
            Y=self.Y,
        )
        update_junction_capacitance_state(
            state,
            self.config,
            self.gas_constant,
            self.cp,
            self.volume_m3,
            dt,
            mdot_in,
            Hdot_in,
            Ydot_in,
            mdot_out,
            Hdot_out,
            Ydot_out,
        )
        self.m_total = state.m_total
        self.E_total = state.E_total
        self.mY = state.mY
        self.p = state.p
        self.T = state.T
        self.Y = state.Y
        return self.totals()

    def update_from_leg_fluxes(
        self,
        dt: float,
        leg_fluxes: Iterable[Tuple[float, float, float]],
    ) -> Tuple[float, float, float]:
        mdot_in = 0.0
        Hdot_in = 0.0
        Ydot_in = 0.0
        mdot_out = 0.0
        Hdot_out = 0.0
        Ydot_out = 0.0
        for mdot, Hdot, Ydot in leg_fluxes:
            if mdot >= 0.0:
                mdot_in += mdot
                Hdot_in += Hdot
                Ydot_in += Ydot
            else:
                mdot_out += -mdot
                Hdot_out += -Hdot
                Ydot_out += -Ydot

        state = JunctionCapacitanceState(
            m_total=self.m_total,
            E_total=self.E_total,
            mY=self.mY,
            p=self.p,
            T=self.T,
            Y=self.Y,
        )
        update_junction_capacitance_state(
            state,
            self.config,
            self.gas_constant,
            self.cp,
            self.volume_m3,
            dt,
            mdot_in,
            Hdot_in,
            Ydot_in,
            mdot_out,
            Hdot_out,
            Ydot_out,
        )
        self.m_total = state.m_total
        self.E_total = state.E_total
        self.mY = state.mY
        self.p = state.p
        self.T = state.T
        self.Y = state.Y
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
