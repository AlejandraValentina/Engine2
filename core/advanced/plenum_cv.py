from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class PlenumHeatTransferConfig:
    enabled: bool = False
    h_w_per_m2k: float = 0.0
    area_m2: float = 0.0
    wall_temp_k: float = 450.0
    clamp_qdot: float = 2e6

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "h_w_per_m2k": self.h_w_per_m2k,
            "area_m2": self.area_m2,
            "wall_temp_k": self.wall_temp_k,
            "clamp_qdot": self.clamp_qdot,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlenumHeatTransferConfig":
        return cls(
            enabled=bool(data.get("enabled", False)),
            h_w_per_m2k=float(data.get("h_w_per_m2k", 0.0)),
            area_m2=float(data.get("area_m2", 0.0)),
            wall_temp_k=float(data.get("wall_temp_k", 450.0)),
            clamp_qdot=float(data.get("clamp_qdot", 2e6)),
        )


@dataclass
class IntakePlenumConfig:
    enabled: bool = False
    volume_m3: float = 0.0
    p_init_pa: float | None = None
    t_init_k: float | None = None
    y_init: float = 1.0
    p_floor_pa: float = 20000.0
    t_floor_k: float = 200.0
    under_relax_alpha: float = 1.0
    heat_transfer: PlenumHeatTransferConfig = field(default_factory=PlenumHeatTransferConfig)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "volume_m3": self.volume_m3,
            "p_init_pa": self.p_init_pa,
            "t_init_k": self.t_init_k,
            "y_init": self.y_init,
            "p_floor_pa": self.p_floor_pa,
            "t_floor_k": self.t_floor_k,
            "under_relax_alpha": self.under_relax_alpha,
            "heat_transfer": self.heat_transfer.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IntakePlenumConfig":
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
            p_init_pa=float(p_init_pa) if p_init_pa is not None else None,
            t_init_k=float(t_init_k) if t_init_k is not None else None,
            y_init=float(y_init) if y_init is not None else 1.0,
            p_floor_pa=float(p_floor_pa) if p_floor_pa is not None else 20000.0,
            t_floor_k=float(t_floor_k) if t_floor_k is not None else 200.0,
            under_relax_alpha=float(data.get("under_relax_alpha", 1.0)),
            heat_transfer=PlenumHeatTransferConfig.from_dict(data.get("heat_transfer", {})),
        )


def validate_plenum_config(cfg: IntakePlenumConfig) -> None:
    if not cfg.enabled:
        return
    if cfg.volume_m3 <= 0.0:
        raise ValueError("intake_plenum.volume_m3 must be positive when enabled")
    if cfg.p_init_pa is not None and cfg.p_init_pa <= 0.0:
        raise ValueError("intake_plenum.p_init_pa must be positive when provided")
    if cfg.t_init_k is not None and cfg.t_init_k <= 0.0:
        raise ValueError("intake_plenum.t_init_k must be positive when provided")
    if not (0.0 <= cfg.y_init <= 1.0):
        raise ValueError("intake_plenum.y_init must be within [0, 1]")
    if cfg.p_floor_pa <= 0.0:
        raise ValueError("intake_plenum.p_floor_pa must be positive")
    if cfg.t_floor_k <= 0.0:
        raise ValueError("intake_plenum.t_floor_k must be positive")
    if cfg.under_relax_alpha < 0.0:
        raise ValueError("intake_plenum.under_relax_alpha must be non-negative")
    if cfg.heat_transfer.enabled:
        if cfg.heat_transfer.h_w_per_m2k <= 0.0:
            raise ValueError("intake_plenum.heat_transfer.h_w_per_m2k must be positive when enabled")
        if cfg.heat_transfer.area_m2 <= 0.0:
            raise ValueError("intake_plenum.heat_transfer.area_m2 must be positive when enabled")
        if cfg.heat_transfer.wall_temp_k <= 0.0:
            raise ValueError("intake_plenum.heat_transfer.wall_temp_k must be positive when enabled")
        if cfg.heat_transfer.clamp_qdot <= 0.0:
            raise ValueError("intake_plenum.heat_transfer.clamp_qdot must be positive when enabled")


@dataclass
class PlenumState:
    m_total: float
    E_total: float
    mY: float
    p: float
    T: float
    Y: float


def _cv_from_cp(cp: float, gas_constant: float) -> float:
    cv = cp - gas_constant
    if cv <= 0.0:
        raise ValueError("Invalid cp/gas_constant for plenum")
    return cv


def _min_mass(cfg: IntakePlenumConfig, volume_m3: float, gas_constant: float) -> float:
    t_floor = max(cfg.t_floor_k, 1e-6)
    return max(1e-9, cfg.p_floor_pa * volume_m3 / (gas_constant * t_floor))


def _heat_transfer_qdot(cfg: PlenumHeatTransferConfig, T_gas: float) -> float:
    if not cfg.enabled:
        return 0.0
    qdot = cfg.h_w_per_m2k * cfg.area_m2 * (T_gas - cfg.wall_temp_k)
    if not math.isfinite(qdot):
        raise ValueError("Plenum heat transfer produced non-finite qdot")
    if abs(qdot) > cfg.clamp_qdot:
        raise ValueError("Plenum heat transfer exceeds clamp_qdot")
    return qdot


def init_plenum_state_from_config(
    cfg: IntakePlenumConfig,
    gas_constant: float,
    cp: float,
    gamma: float,
    *,
    p_amb: float,
    t_amb: float,
    y_amb: float,
    p_init_override: float | None = None,
    t_init_override: float | None = None,
    y_init_override: float | None = None,
) -> PlenumState:
    validate_plenum_config(cfg)
    _ = gamma

    p_init = p_init_override
    if p_init is None:
        p_init = cfg.p_init_pa if cfg.p_init_pa is not None else p_amb
    t_init = t_init_override
    if t_init is None:
        t_init = cfg.t_init_k if cfg.t_init_k is not None else t_amb
    y_init = y_init_override if y_init_override is not None else cfg.y_init

    y_init = min(max(float(y_init), 0.0), 1.0)
    p_init = max(float(p_init), cfg.p_floor_pa)
    t_init = max(float(t_init), cfg.t_floor_k)

    volume_m3 = max(cfg.volume_m3, 1e-12)
    cv = _cv_from_cp(cp, gas_constant)
    m_min = _min_mass(cfg, volume_m3, gas_constant)

    m_total = max(p_init * volume_m3 / (gas_constant * max(t_init, 1e-6)), m_min)
    E_total = m_total * cv * max(t_init, 1e-6)
    mY = m_total * y_init
    return PlenumState(
        m_total=m_total,
        E_total=E_total,
        mY=mY,
        p=p_init,
        T=t_init,
        Y=y_init,
    )


def update_plenum_state(
    state: PlenumState,
    cfg: IntakePlenumConfig,
    gas_constant: float,
    cp: float,
    volume_m3: float,
    dt: float,
    mdot_throttle: float,
    Hdot_throttle: float,
    Ydot_throttle: float,
    mdot_pipe: float,
    Hdot_pipe: float,
    Ydot_pipe: float,
) -> None:
    if not cfg.enabled or dt <= 0.0:
        return

    cv = _cv_from_cp(cp, gas_constant)
    volume_m3 = max(volume_m3, 1e-12)
    m_min = _min_mass(cfg, volume_m3, gas_constant)
    qdot_ht = _heat_transfer_qdot(cfg.heat_transfer, state.T)

    mdot_in = max(mdot_throttle, 0.0) + max(-mdot_pipe, 0.0)
    mdot_out = max(-mdot_throttle, 0.0) + max(mdot_pipe, 0.0)
    Hdot_in = max(Hdot_throttle, 0.0) + max(-Hdot_pipe, 0.0)
    Hdot_out = max(-Hdot_throttle, 0.0) + max(Hdot_pipe, 0.0)
    Ydot_in = max(Ydot_throttle, 0.0) + max(-Ydot_pipe, 0.0)
    Ydot_out = max(-Ydot_throttle, 0.0) + max(Ydot_pipe, 0.0)

    state.m_total = max(state.m_total + (mdot_in - mdot_out) * dt, m_min)
    state.E_total = max(state.E_total + (Hdot_in - Hdot_out - qdot_ht) * dt, 1e-9)
    state.mY = state.mY + (Ydot_in - Ydot_out) * dt

    Y_new = state.mY / max(state.m_total, 1e-12)
    Y_new = min(max(Y_new, 0.0), 1.0)
    state.mY = state.m_total * Y_new

    T_new = state.E_total / max(state.m_total * cv, 1e-12)
    if T_new < cfg.t_floor_k:
        T_new = cfg.t_floor_k

    rho = state.m_total / volume_m3
    p_new = rho * gas_constant * T_new
    if p_new < cfg.p_floor_pa:
        p_new = cfg.p_floor_pa
        T_new = max(p_new * volume_m3 / (state.m_total * gas_constant), cfg.t_floor_k)

    alpha = max(float(cfg.under_relax_alpha), 0.0)
    T_relaxed = state.T + alpha * (T_new - state.T)
    if T_relaxed < cfg.t_floor_k:
        T_relaxed = cfg.t_floor_k

    p_relaxed = rho * gas_constant * T_relaxed
    if p_relaxed < cfg.p_floor_pa:
        p_relaxed = cfg.p_floor_pa
        T_relaxed = max(p_relaxed * volume_m3 / (state.m_total * gas_constant), cfg.t_floor_k)
        p_relaxed = rho * gas_constant * T_relaxed

    state.T = T_relaxed
    state.p = p_relaxed
    state.Y = Y_new
    state.E_total = state.m_total * cv * state.T


class PlenumControlVolume:
    def __init__(
        self,
        config: IntakePlenumConfig,
        gas_constant: float,
        cp: float,
        gamma: float,
        *,
        p_amb: float | None = None,
        T_amb: float | None = None,
        Y_amb: float | None = None,
        p_init: float | None = None,
        T_init: float | None = None,
        Y_init: float | None = None,
    ) -> None:
        validate_plenum_config(config)
        self.config = config
        self.gas_constant = gas_constant
        self.cp = cp
        self.gamma = gamma
        self.volume_m3 = max(config.volume_m3, 1e-12)
        self.cv = _cv_from_cp(cp, gas_constant)

        p_amb_val = 101325.0 if p_amb is None else float(p_amb)
        t_amb_val = 300.0 if T_amb is None else float(T_amb)
        y_amb_val = 1.0 if Y_amb is None else float(Y_amb)

        self.state = init_plenum_state_from_config(
            config,
            gas_constant,
            cp,
            gamma,
            p_amb=p_amb_val,
            t_amb=t_amb_val,
            y_amb=y_amb_val,
            p_init_override=p_init,
            t_init_override=T_init,
            y_init_override=Y_init,
        )

    @property
    def m_total(self) -> float:
        return self.state.m_total

    @property
    def E_total(self) -> float:
        return self.state.E_total

    @property
    def mY(self) -> float:
        return self.state.mY

    @property
    def p(self) -> float:
        return self.state.p

    @property
    def T(self) -> float:
        return self.state.T

    @property
    def Y(self) -> float:
        return self.state.Y

    def clone(self) -> "PlenumControlVolume":
        clone = PlenumControlVolume(
            self.config,
            self.gas_constant,
            self.cp,
            self.gamma,
        )
        clone.volume_m3 = self.volume_m3
        clone.cv = self.cv
        clone.state = PlenumState(
            m_total=self.state.m_total,
            E_total=self.state.E_total,
            mY=self.state.mY,
            p=self.state.p,
            T=self.state.T,
            Y=self.state.Y,
        )
        return clone

    def update(
        self,
        dt: float,
        mdot_throttle: float,
        Hdot_throttle: float,
        Ydot_throttle: float,
        mdot_pipe: float,
        Hdot_pipe: float,
        Ydot_pipe: float,
    ) -> None:
        update_plenum_state(
            self.state,
            self.config,
            self.gas_constant,
            self.cp,
            self.volume_m3,
            dt,
            mdot_throttle,
            Hdot_throttle,
            Ydot_throttle,
            mdot_pipe,
            Hdot_pipe,
            Ydot_pipe,
        )
