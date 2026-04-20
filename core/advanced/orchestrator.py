from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.advanced.combustion import CombustionConfig, combustion_qdot
from core.advanced.coupling import (
    ValveTiming,
    boundary_flux_from_nozzle,
    ghost_state_from_nozzle,
    reset_ghost_counters,
)
from core.advanced.cylinder_cv import CylinderControlVolume, HeatTransferConfig, slider_crank_volume
from core.advanced.plenum_cv import (
    ExhaustPlenumConfig,
    IntakePlenumConfig,
    PlenumControlVolume,
    validate_plenum_config,
)
from core.advanced.wall_thermal import (
    init_wall_temperature,
    validate_wall_thermal_config,
    wall_thermal_step,
    _dittus_boelter_h_array,
)
from core.advanced.state import Primitive1D, primitive_to_conserved, stagnation_from_static
from core.advanced.solver_1d import (
    ShockCFLConfig,
    cfl_dt,
    conserved_to_primitive,
    muscl_hancock_step,
    shock_cfl_plan,
    validate_shock_cfl_config,
)
from core.advanced.nozzle import nozzle_mass_flow
from core.engine_components import Engine, FuelConfig, Throttle, WallThermalConfig

try:
    from core.advanced.solver_1d import reset_guard_counters
except ImportError:  # pragma: no cover - compat for older solver_1d
    def reset_guard_counters() -> None:
        return None


@dataclass
class ThrottleLoadMap:
    load_grid: List[float] = field(default_factory=list)
    position_grid: List[float] = field(default_factory=list)

    def position_for_load(self, load: float) -> float:
        if not self.load_grid or not self.position_grid:
            raise ValueError("throttle_position_from_load requires non-empty grids")
        if len(self.load_grid) != len(self.position_grid):
            raise ValueError("throttle_position_from_load grids must match in length")
        if len(self.load_grid) == 1:
            return self.position_grid[0]

        load_clamped = min(max(load, self.load_grid[0]), self.load_grid[-1])
        for idx in range(len(self.load_grid) - 1):
            lo = self.load_grid[idx]
            hi = self.load_grid[idx + 1]
            if hi <= lo:
                continue
            if load_clamped <= hi:
                t = (load_clamped - lo) / (hi - lo)
                pos = self.position_grid[idx] + t * (self.position_grid[idx + 1] - self.position_grid[idx])
                return pos
        return self.position_grid[-1]


@dataclass
class SweepConfig:
    enabled: bool = False
    rpm_start: float = 3000.0
    rpm_end: float = 9000.0
    rpm_step: float = 250.0
    ramp_mode: str = "step"
    seconds_per_step: float = 0.2
    cycles_per_step: int = 3
    carry_state: bool = True
    record_every_step: bool = True
    abort_on_fail: bool = False
    throttle_position_grid: Optional[List[float]] = None
    throttle_position_from_load: Optional[ThrottleLoadMap] = None
    record_part_load_metrics: bool = False


@dataclass
class OrchestratorConfig:
    gamma: float = 1.35
    gas_constant: float = 287.0
    cp: Optional[float] = None
    cp_model: str = "constant"
    cfl: float = 0.5
    dt_max: float = 5e-5
    max_cycles: int = 5
    convergence_tol: float = 0.005
    coupling_phase: str = "phase2"
    outlet_mode: str = "non_reflecting"
    p_outlet: Optional[float] = None
    outlet_reflection: Optional[float] = None
    outlet_impedance: Optional[float] = None
    enable_friction: bool = False
    friction_model: str = "swamee-jain"
    friction_energy_mode: str = "wall_loss"
    roughness_m: float = 0.0
    mu: float = 1.8e-5
    loss_coeff: float = 0.0
    pipe_role: str = "intake"
    initial_Y: Optional[float] = None
    periodicity_tol: float = 0.01
    periodicity_required: int = 2
    combustion: CombustionConfig = field(default_factory=CombustionConfig)
    coupling_relax_alpha: float = 1.0
    coupling_relax_warmup_iters: int = 0
    use_numba_1d: bool = False
    heat_transfer: HeatTransferConfig = field(default_factory=HeatTransferConfig)
    throttle: Throttle = field(default_factory=Throttle)
    pipe_prefill: "PipePrefillConfig" = field(default_factory=lambda: PipePrefillConfig())
    valve_closed_wall_bc: "ValveClosedWallBCConfig" = field(default_factory=lambda: ValveClosedWallBCConfig())
    intake_plenum: IntakePlenumConfig = field(default_factory=IntakePlenumConfig)
    exhaust_plenum: ExhaustPlenumConfig = field(default_factory=ExhaustPlenumConfig)
    sweep: SweepConfig = field(default_factory=SweepConfig)
    fuel: FuelConfig = field(default_factory=FuelConfig)
    wall_thermal: WallThermalConfig = field(default_factory=WallThermalConfig)
    enable_pumping_work: bool = False
    shock_cfl: ShockCFLConfig = field(default_factory=ShockCFLConfig)

    def __post_init__(self) -> None:
        if self.cp is None:
            self.cp = self.gamma * self.gas_constant / max(self.gamma - 1.0, 1e-9)
        if self.periodicity_tol < 0.0:
            raise ValueError("periodicity_tol must be non-negative")
        if self.periodicity_required < 1:
            raise ValueError("periodicity_required must be >= 1")
        if self.friction_model not in ("swamee-jain", "constant"):
            raise ValueError("friction_model must be 'swamee-jain' or 'constant'")
        if self.friction_energy_mode not in ("wall_loss", "adiabatic"):
            raise ValueError("friction_energy_mode must be 'wall_loss' or 'adiabatic'")
        if self.coupling_relax_alpha < 0.0:
            raise ValueError("coupling_relax_alpha must be >= 0")
        if self.coupling_relax_warmup_iters < 0:
            raise ValueError("coupling_relax_warmup_iters must be >= 0")
        if self.cp_model not in ("constant", "nasa7"):
            raise ValueError("cp_model must be 'constant' or 'nasa7'")
        validate_shock_cfl_config(self.shock_cfl)
        if self.throttle.enabled:
            if self.throttle.body_diam_m <= 0.0:
                raise ValueError("throttle.body_diam_m must be positive when enabled")
            if self.throttle.area_exponent <= 0.0:
                raise ValueError("throttle.area_exponent must be positive when enabled")
            if self.throttle.rate_limit_per_s is not None and self.throttle.rate_limit_per_s < 0.0:
                raise ValueError("throttle.rate_limit_per_s must be non-negative when enabled")
            if self.throttle.cd <= 0.0:
                raise ValueError("throttle.cd must be positive when enabled")
        if self.pipe_prefill.enabled:
            if self.pipe_prefill.auto:
                _validate_prefill_auto(self.pipe_prefill)
            else:
                _validate_prefill_state(self.pipe_prefill.intake, "pipe_prefill.intake")
                _validate_prefill_state(self.pipe_prefill.exhaust, "pipe_prefill.exhaust")
        if self.valve_closed_wall_bc.enabled and self.valve_closed_wall_bc.area_eps_m2 <= 0.0:
            raise ValueError("valve_closed_wall_bc.area_eps_m2 must be positive when enabled")
        validate_wall_thermal_config(self.wall_thermal)
        validate_plenum_config(self.intake_plenum, label="intake_plenum")
        validate_plenum_config(self.exhaust_plenum, label="exhaust_plenum")
        if self.sweep.enabled:
            if self.sweep.ramp_mode not in ("step", "linear_time"):
                raise ValueError("sweep.ramp_mode must be 'step' or 'linear_time'")
            if self.sweep.rpm_step <= 0.0:
                raise ValueError("sweep.rpm_step must be positive")
            if self.sweep.cycles_per_step < 1:
                raise ValueError("sweep.cycles_per_step must be >= 1")
            if self.sweep.ramp_mode == "linear_time" and self.sweep.seconds_per_step <= 0.0:
                raise ValueError("sweep.seconds_per_step must be positive for linear_time")
        _validate_sweep_throttle(self.sweep)
        if self.fuel.enabled:
            if self.fuel.mode not in ("lambda", "afr"):
                raise ValueError("fuel.mode must be 'lambda' or 'afr'")
            if self.fuel.afr_stoich <= 0.0:
                raise ValueError("fuel.afr_stoich must be positive")
            if self.fuel.lhv_j_per_kg <= 0.0:
                raise ValueError("fuel.lhv_j_per_kg must be positive")
            if self.fuel.eta_comb <= 0.0:
                raise ValueError("fuel.eta_comb must be positive")
            if self.fuel.clamp_lambda_min <= 0.0:
                raise ValueError("fuel.clamp_lambda_min must be positive")
            if self.fuel.clamp_lambda_max <= 0.0:
                raise ValueError("fuel.clamp_lambda_max must be positive")
            if self.fuel.clamp_lambda_max < self.fuel.clamp_lambda_min:
                raise ValueError("fuel.clamp_lambda_max must be >= clamp_lambda_min")
            if self.fuel.bsfc_units != "g_per_kwh":
                raise ValueError("fuel.bsfc_units must be 'g_per_kwh'")


@dataclass
class PipePrefillState:
    p_Pa: float = 101325.0
    T_K: float = 300.0
    Y: float = 1.0


@dataclass
class PipePrefillConfig:
    enabled: bool = False
    auto: bool = False
    auto_amb_p_Pa: float = 101325.0
    auto_amb_T_K: float = 300.0
    exhaust_prefill_T_K: float = 700.0
    intake: PipePrefillState = field(default_factory=PipePrefillState)
    exhaust: PipePrefillState = field(
        default_factory=lambda: PipePrefillState(p_Pa=101325.0, T_K=700.0, Y=0.0)
    )


@dataclass
class ValveClosedWallBCConfig:
    enabled: bool = False
    area_eps_m2: float = 1e-7


@dataclass
class _OrchestratorState:
    U: np.ndarray
    cyl: CylinderControlVolume
    rho0: float
    p0: float
    T0: float
    Y_init: float
    twall_pipe_k: float
    throttle_pos: float
    plenum: Optional[PlenumControlVolume]
    exhaust_plenum: Optional[PlenumControlVolume]


def _validate_prefill_state(state: PipePrefillState, label: str) -> None:
    if state.p_Pa <= 0.0:
        raise ValueError(f"{label}.p_Pa must be positive")
    if state.T_K <= 0.0:
        raise ValueError(f"{label}.T_K must be positive")
    if not (0.0 <= state.Y <= 1.0):
        raise ValueError(f"{label}.Y must be within [0, 1]")


def _validate_prefill_auto(cfg: PipePrefillConfig) -> None:
    if cfg.auto_amb_p_Pa <= 0.0:
        raise ValueError("pipe_prefill.auto_amb_p_Pa must be positive")
    if cfg.auto_amb_T_K <= 0.0:
        raise ValueError("pipe_prefill.auto_amb_T_K must be positive")
    if cfg.exhaust_prefill_T_K <= 0.0:
        raise ValueError("pipe_prefill.exhaust_prefill_T_K must be positive")


def _validate_sweep_throttle(cfg: SweepConfig) -> None:
    if not cfg.enabled:
        return
    grid = cfg.throttle_position_grid
    load_map = cfg.throttle_position_from_load
    if grid is not None and load_map is not None:
        raise ValueError("sweep throttle_position_grid and throttle_position_from_load are mutually exclusive")
    if grid is not None:
        _validate_throttle_position_grid(grid)
    if load_map is not None:
        _validate_throttle_load_map(load_map)


def _validate_throttle_position_grid(grid: List[float]) -> None:
    if not grid:
        raise ValueError("sweep throttle_position_grid cannot be empty")
    for value in grid:
        if not (0.0 <= float(value) <= 1.0):
            raise ValueError("sweep throttle_position_grid values must be within [0, 1]")


def _validate_throttle_load_map(load_map: ThrottleLoadMap) -> None:
    if not load_map.load_grid or not load_map.position_grid:
        raise ValueError("sweep throttle_position_from_load requires non-empty grids")
    if len(load_map.load_grid) != len(load_map.position_grid):
        raise ValueError("sweep throttle_position_from_load grids must match in length")
    if any(load_map.load_grid[i] > load_map.load_grid[i + 1] for i in range(len(load_map.load_grid) - 1)):
        raise ValueError("sweep throttle_position_from_load load_grid must be non-decreasing")
    for value in load_map.position_grid:
        if not (0.0 <= float(value) <= 1.0):
            raise ValueError("sweep throttle_position_from_load positions must be within [0, 1]")


def _init_pipe_state(
    cfg: OrchestratorConfig, pipe_cells: int
) -> tuple[np.ndarray, float, float, float, float]:
    if cfg.pipe_prefill.enabled:
        if cfg.pipe_prefill.auto:
            p0 = float(cfg.pipe_prefill.auto_amb_p_Pa)
            if cfg.pipe_role == "intake":
                T0 = float(cfg.pipe_prefill.auto_amb_T_K)
                Y_init = 1.0
            else:
                T0 = float(cfg.pipe_prefill.exhaust_prefill_T_K)
                Y_init = 0.0
        else:
            state = cfg.pipe_prefill.intake if cfg.pipe_role == "intake" else cfg.pipe_prefill.exhaust
            p0 = float(state.p_Pa)
            T0 = float(state.T_K)
            Y_init = float(state.Y)
        rho0 = p0 / (cfg.gas_constant * max(T0, 1e-9))
    else:
        rho0 = 1.2
        p0 = 101325.0
        T0 = p0 / (rho0 * cfg.gas_constant)
        if cfg.initial_Y is not None:
            Y_init = cfg.initial_Y
        else:
            Y_init = 0.0 if cfg.pipe_role == "exhaust" else 1.0
    if cfg.initial_Y is not None:
        Y_init = cfg.initial_Y
    if not (0.0 <= Y_init <= 1.0):
        raise ValueError("initial_Y must be within [0, 1]")
    E0 = cfg.gas_constant * T0 / (cfg.gamma - 1.0)
    U = np.zeros((pipe_cells + 2, 4))
    U[1:-1, 0] = rho0
    U[1:-1, 1] = 0.0
    U[1:-1, 2] = rho0 * E0
    U[1:-1, 3] = rho0 * Y_init
    U[0] = U[1]
    U[-1] = U[-2]
    return U, rho0, p0, T0, Y_init


def _resolve_ambient_totals(cfg: OrchestratorConfig, p0: float, T0: float) -> tuple[float, float, float]:
    p_amb = cfg.throttle.p0_amb_Pa if cfg.throttle.p0_amb_Pa is not None else p0
    T_amb = cfg.throttle.T0_amb_K if cfg.throttle.T0_amb_K is not None else T0
    Y_amb = cfg.throttle.Y0_amb if cfg.throttle.Y0_amb is not None else 1.0
    Y_amb = min(max(float(Y_amb), 0.0), 1.0)
    return float(p_amb), float(T_amb), float(Y_amb)


def _resolve_exhaust_plenum_defaults(p0: float, T0: float, Y_init: float) -> tuple[float, float, float]:
    return float(p0), float(T0), min(max(float(Y_init), 0.0), 1.0)


def _pipe_mean_temperature(U: np.ndarray, gamma: float, gas_constant: float) -> float:
    prim = conserved_to_primitive(U[1:-1], gamma, gas_constant)
    rho = prim[:, 0]
    T = prim[:, 3]
    mass = float(np.sum(rho))
    if mass <= 0.0:
        return float(np.mean(T))
    return float(np.sum(rho * T) / mass)


def _apply_pipe_wall_thermal(
    U: np.ndarray,
    dt: float,
    cfg: WallThermalConfig,
    twall_k: float,
    pipe_volume: float,
    gamma: float,
    gas_constant: float,
) -> float:
    if not cfg.enabled:
        return twall_k
    if pipe_volume <= 0.0:
        raise ValueError("pipe_volume must be positive for wall_thermal")

    prim = conserved_to_primitive(U[1:-1], gamma, gas_constant)
    rho = prim[:, 0]
    u = prim[:, 1]
    T_gas = _pipe_mean_temperature(U, gamma, gas_constant)
    mass = float(np.sum(rho))
    rho_mean = float(np.mean(rho)) if rho.size > 0 else 0.0
    u_mean = float(np.sum(np.abs(u) * rho) / mass) if mass > 0.0 else 0.0
    cp = gamma * gas_constant / max(gamma - 1.0, 1e-9)
    diameter = 4.0 * pipe_volume / cfg.area_m2 if cfg.area_m2 > 0.0 else None
    if cfg.h_model == "dittus_boelter":
        if diameter is None or diameter <= 0.0:
            return twall_k
        h_vals = _dittus_boelter_h_array(prim[:, 3], rho, u, diameter, cfg, cp)
        h_vals = np.maximum(h_vals * cfg.h_mult, 0.0)
        area_per_vol = cfg.area_m2 / pipe_volume
        qdot_cells = h_vals * area_per_vol * (prim[:, 3] - twall_k)
        delta_e = -qdot_cells * dt
        U[1:-1, 2] += delta_e
        rho = U[1:-1, 0]
        mom = U[1:-1, 1]
        rho_safe = np.maximum(rho, 1e-12)
        u = mom / rho_safe
        kinetic = 0.5 * rho_safe * u * u
        U[1:-1, 2] = np.maximum(U[1:-1, 2], kinetic + 1e-9)

        qdot_total = float(np.sum(h_vals * (prim[:, 3] - twall_k))) * (cfg.area_m2 / max(len(h_vals), 1))
        denom = cfg.m_wall_kg * cfg.cp_wall_j_per_kgk
        if denom <= 0.0:
            raise ValueError("wall_thermal m_wall_kg and cp_wall_j_per_kgk must be positive")
        twall_new = twall_k + qdot_total * dt / denom
        twall_new = min(max(twall_new, cfg.twall_min_k), cfg.twall_max_k)
        return twall_new

    twall_k, qdot = wall_thermal_step(
        twall_k,
        T_gas,
        dt,
        cfg,
        rho=rho_mean,
        u=u_mean,
        diameter_m=diameter,
        cp=cp,
    )
    if qdot != 0.0:
        delta_e = -qdot * dt / pipe_volume
        U[1:-1, 2] += delta_e
        rho = U[1:-1, 0]
        mom = U[1:-1, 1]
        rho_safe = np.maximum(rho, 1e-12)
        u = mom / rho_safe
        kinetic = 0.5 * rho_safe * u * u
        U[1:-1, 2] = np.maximum(U[1:-1, 2], kinetic + 1e-9)
    return twall_k


def _build_initial_state(cfg: OrchestratorConfig, pipe_cells: int, clearance_m3: float) -> _OrchestratorState:
    U, rho0, p0, T0, Y_init = _init_pipe_state(cfg, pipe_cells)
    cyl = CylinderControlVolume(
        m_total=rho0 * clearance_m3,
        m_fresh=rho0 * clearance_m3,
        T=T0,
        p=p0,
        V=clearance_m3,
        gamma=cfg.gamma,
        gas_constant=cfg.gas_constant,
        heat_transfer=cfg.heat_transfer,
    )
    twall_pipe_k = init_wall_temperature(cfg.wall_thermal)
    throttle_pos = _clamp_throttle_position(cfg.throttle.position)
    plenum = None
    exhaust_plenum = None
    if cfg.intake_plenum.enabled and cfg.pipe_role == "intake":
        p_amb, T_amb, Y_amb = _resolve_ambient_totals(cfg, p0, T0)
        plenum = PlenumControlVolume(
            cfg.intake_plenum,
            cfg.gas_constant,
            cfg.cp,
            cfg.gamma,
            p_amb=p_amb,
            T_amb=T_amb,
            Y_amb=Y_amb,
        )
    if cfg.exhaust_plenum.enabled and cfg.pipe_role == "exhaust" and cfg.exhaust_plenum.apply_to == "exhaust_only":
        p_def, T_def, Y_def = _resolve_exhaust_plenum_defaults(p0, T0, Y_init)
        exhaust_plenum = PlenumControlVolume(
            cfg.exhaust_plenum,
            cfg.gas_constant,
            cfg.cp,
            cfg.gamma,
            p_amb=p_def,
            T_amb=T_def,
            Y_amb=Y_def,
        )
    return _OrchestratorState(
        U=U,
        cyl=cyl,
        rho0=rho0,
        p0=p0,
        T0=T0,
        Y_init=Y_init,
        twall_pipe_k=twall_pipe_k,
        throttle_pos=throttle_pos,
        plenum=plenum,
        exhaust_plenum=exhaust_plenum,
    )


def _clone_state(state: _OrchestratorState, cfg: OrchestratorConfig) -> _OrchestratorState:
    cyl = CylinderControlVolume(
        m_total=state.cyl.m_total,
        m_fresh=state.cyl.m_fresh,
        T=state.cyl.T,
        p=state.cyl.p,
        V=state.cyl.V,
        gamma=cfg.gamma,
        gas_constant=cfg.gas_constant,
        heat_transfer=state.cyl.heat_transfer,
    )
    plenum = state.plenum.clone() if state.plenum is not None else None
    exhaust_plenum = state.exhaust_plenum.clone() if state.exhaust_plenum is not None else None
    return _OrchestratorState(
        U=state.U.copy(),
        cyl=cyl,
        rho0=state.rho0,
        p0=state.p0,
        T0=state.T0,
        Y_init=state.Y_init,
        twall_pipe_k=state.twall_pipe_k,
        throttle_pos=state.throttle_pos,
        plenum=plenum,
        exhaust_plenum=exhaust_plenum,
    )


def _build_rpm_grid(cfg: SweepConfig) -> List[float]:
    rpm_start = float(cfg.rpm_start)
    rpm_end = float(cfg.rpm_end)
    step = float(cfg.rpm_step)
    if step <= 0.0:
        raise ValueError("sweep.rpm_step must be positive")
    direction = 1.0 if rpm_end >= rpm_start else -1.0
    step *= direction
    values: List[float] = []
    rpm = rpm_start
    while True:
        values.append(rpm)
        if (direction > 0.0 and rpm >= rpm_end) or (direction < 0.0 and rpm <= rpm_end):
            break
        rpm_next = rpm + step
        if (direction > 0.0 and rpm_next > rpm_end) or (direction < 0.0 and rpm_next < rpm_end):
            rpm = rpm_end
        else:
            rpm = rpm_next
    return values


def _sweep_load_fraction(step_index: int, total_steps: int) -> float:
    if total_steps <= 1:
        return 0.0
    return step_index / float(total_steps - 1)


def _resolve_sweep_throttle_position(cfg: SweepConfig, step_index: int, total_steps: int) -> Optional[float]:
    if cfg.throttle_position_grid is not None:
        grid = cfg.throttle_position_grid
        index = min(max(step_index, 0), len(grid) - 1)
        return float(grid[index])
    if cfg.throttle_position_from_load is not None:
        load = _sweep_load_fraction(step_index, total_steps)
        return float(cfg.throttle_position_from_load.position_for_load(load))
    return None


def _state_is_finite(U: np.ndarray, cyl: CylinderControlVolume) -> bool:
    if not np.isfinite(U).all():
        return False
    return all(
        math.isfinite(val)
        for val in (
            cyl.m_total,
            cyl.m_fresh,
            cyl.T,
            cyl.p,
            cyl.V,
        )
    )


def _fuel_afr_lambda(cfg: FuelConfig) -> tuple[float, float]:
    if cfg.mode == "lambda":
        lambda_raw = cfg.lambda_target
    else:
        lambda_raw = cfg.afr_target / max(cfg.afr_stoich, 1e-12)
    lambda_used = min(max(lambda_raw, cfg.clamp_lambda_min), cfg.clamp_lambda_max)
    afr_used = cfg.afr_stoich * lambda_used
    return afr_used, lambda_used


def _bsfc_g_per_kwh(fuel_flow_kg_s: float, brake_power_w: float, eps: float = 1e-12) -> Optional[float]:
    if brake_power_w <= eps:
        return None
    return (fuel_flow_kg_s * 1e3 * 3600.0) / (brake_power_w / 1000.0)


def _compute_fuel_metrics(
    m_air_fresh_per_cycle_kg: float,
    rpm: float,
    indicated_work: float,
    cfg: FuelConfig,
    brake_power_w: Optional[float] = None,
) -> dict:
    afr_used, lambda_used = _fuel_afr_lambda(cfg)
    m_fuel_per_cycle_kg = m_air_fresh_per_cycle_kg / max(afr_used, 1e-12)
    cycles_per_second = rpm / 120.0
    fuel_flow_kg_s = m_fuel_per_cycle_kg * cycles_per_second
    fuel_power_w = fuel_flow_kg_s * cfg.lhv_j_per_kg * cfg.eta_comb
    indicated_power_w = indicated_work * cycles_per_second
    brake_power_w = indicated_power_w if brake_power_w is None else brake_power_w
    bsfc = _bsfc_g_per_kwh(fuel_flow_kg_s, brake_power_w)
    eta_bte = brake_power_w / fuel_power_w if fuel_power_w > 0.0 else None
    eta_ite = indicated_power_w / fuel_power_w if fuel_power_w > 0.0 else None
    return {
        "m_air_fresh_per_cycle_kg": float(m_air_fresh_per_cycle_kg),
        "lambda_used": float(lambda_used),
        "afr_used": float(afr_used),
        "m_fuel_per_cycle_kg": float(m_fuel_per_cycle_kg),
        "fuel_flow_kg_s": float(fuel_flow_kg_s),
        "fuel_power_w": float(fuel_power_w),
        "brake_power_w": float(brake_power_w),
        "indicated_power_w": float(indicated_power_w),
        "bsfc_g_per_kwh": float(bsfc) if bsfc is not None else None,
        "eta_bte": float(eta_bte) if eta_bte is not None else None,
        "eta_ite": float(eta_ite) if eta_ite is not None else None,
        "bsfc_units": cfg.bsfc_units,
    }


def _reflective_wall_ghost(
    prim_pipe: np.ndarray, gamma: float, gas_constant: float
) -> np.ndarray:
    prim = Primitive1D(
        rho=float(prim_pipe[0]),
        u=-float(prim_pipe[1]),
        p=float(prim_pipe[2]),
        T=float(prim_pipe[3]),
        Y=float(prim_pipe[4]),
    )
    cons = primitive_to_conserved(prim, gamma, gas_constant)
    return np.array([cons.rho, cons.rhou, cons.rhoE, cons.rhoY], dtype=float)


def _compute_valve_boundary(
    cfg: OrchestratorConfig,
    valve: ValveTiming,
    angle_deg: float,
    cyl: CylinderControlVolume,
    prim_pipe: np.ndarray,
    p0_pipe: float,
    T0_pipe: float,
    Y_pipe: float,
    area_face: float,
    rho_pipe: float,
    u_pipe: float,
) -> tuple[float, float, float, np.ndarray]:
    area_eff = valve.area_eff(angle_deg)
    if cfg.valve_closed_wall_bc.enabled and area_eff < cfg.valve_closed_wall_bc.area_eps_m2:
        ghost = _reflective_wall_ghost(prim_pipe, cfg.gamma, cfg.gas_constant)
        return 0.0, 0.0, 0.0, ghost

    Y_cyl = cyl.m_fresh / max(cyl.m_total, 1e-9)
    mdot, Hdot, Ydot, _ = boundary_flux_from_nozzle(
        cyl.p,
        cyl.T,
        Y_cyl,
        prim_pipe[2],
        valve=valve,
        angle_deg=angle_deg,
        gamma=cfg.gamma,
        gas_constant=cfg.gas_constant,
        cp=cfg.cp,
        cp_model=cfg.cp_model,
        p0_down=p0_pipe,
        T0_down=T0_pipe,
        Y0_down=Y_pipe,
        loss_coeff=cfg.loss_coeff,
        rho_down=rho_pipe,
        u_down=u_pipe,
        area_pipe_m2=area_face,
    )
    if mdot >= 0.0:
        ghost_p = cyl.p
        ghost_T = cyl.T
        ghost_Y = Y_cyl
    else:
        ghost_p = p0_pipe
        ghost_T = T0_pipe
        ghost_Y = Y_pipe
    ghost = ghost_state_from_nozzle(
        ghost_p,
        ghost_T,
        ghost_Y,
        mdot,
        max(area_face, 1e-9),
        cfg.gamma,
        cfg.gas_constant,
        phase=cfg.coupling_phase,
        cp_model=cfg.cp_model,
    )
    return mdot, Hdot, Ydot, ghost


@dataclass
class _FixedAreaValve:
    area_m2: float

    def area_eff(self, angle_deg: float) -> float:
        _ = angle_deg
        return max(self.area_m2, 0.0)


def _throttle_is_active(throttle: Throttle, position: float | None = None) -> bool:
    if not throttle.enabled:
        return False
    pos = _clamp_throttle_position(throttle.position if position is None else position)
    return pos < 1.0


def _throttle_area_eff(throttle: Throttle, position: float | None = None) -> float:
    if throttle.body_diam_m <= 0.0:
        raise ValueError("throttle.body_diam_m must be positive when enabled")
    pos = _clamp_throttle_position(throttle.position if position is None else position)
    exponent = _throttle_area_exponent(throttle)
    area_max = math.pi * (throttle.body_diam_m * 0.5) ** 2
    return throttle.cd * area_max * (pos ** exponent)


def _clamp_throttle_position(position: float) -> float:
    return min(max(position, 0.0), 1.0)


def _throttle_area_exponent(throttle: Throttle) -> float:
    if throttle.safety_clamps:
        return max(throttle.area_exponent, 1.0)
    return throttle.area_exponent


def _update_throttle_position(
    prev_position: float,
    commanded_position: float,
    dt: float,
    rate_limit_per_s: float | None,
) -> float:
    prev = _clamp_throttle_position(prev_position)
    commanded = _clamp_throttle_position(commanded_position)
    if rate_limit_per_s is None or rate_limit_per_s <= 0.0 or dt <= 0.0:
        return commanded
    max_delta = rate_limit_per_s * dt
    delta = commanded - prev
    if abs(delta) <= max_delta:
        return commanded
    return prev + math.copysign(max_delta, delta)


def _relax_downstream_totals(
    prev: Optional[Tuple[float, float, float]],
    current: Tuple[float, float, float],
    alpha: float,
    iter_index: int,
    warmup_iters: int,
    p_floor: float = 1e-6,
    t_floor: float = 1e-6,
) -> Tuple[Tuple[float, float, float], float]:
    alpha_clamped = max(min(alpha, 1.0), 0.0)
    if warmup_iters > 0:
        t = min(iter_index + 1, warmup_iters) / float(warmup_iters)
        alpha_eff = alpha_clamped + (1.0 - alpha_clamped) * t
    else:
        alpha_eff = alpha_clamped

    if prev is None:
        p_rel, t_rel, y_rel = current
    else:
        p_rel = (1.0 - alpha_eff) * prev[0] + alpha_eff * current[0]
        t_rel = (1.0 - alpha_eff) * prev[1] + alpha_eff * current[1]
        y_rel = (1.0 - alpha_eff) * prev[2] + alpha_eff * current[2]

    p_rel = max(p_rel, p_floor)
    t_rel = max(t_rel, t_floor)
    y_rel = min(max(y_rel, 0.0), 1.0)
    return (p_rel, t_rel, y_rel), alpha_eff


class Orchestrator:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.cfg = config

    def run(
        self,
        rpm: float,
        pipe_cells: int,
        pipe_length_m: float,
        pipe_diameter_m: float,
        bore_m: float,
        stroke_m: float,
        conrod_m: float,
        clearance_m3: float,
        valve: ValveTiming,
        junction_totals: Optional[Tuple[float, float, float]] = None,
    ) -> Dict[str, List[float]]:
        reset_guard_counters()
        reset_ghost_counters()
        if self.cfg.sweep.enabled:
            return self._run_sweep(
                pipe_cells,
                pipe_length_m,
                pipe_diameter_m,
                bore_m,
                stroke_m,
                conrod_m,
                clearance_m3,
                valve,
                junction_totals,
            )
        return self._run_steady(
            rpm,
            pipe_cells,
            pipe_length_m,
            pipe_diameter_m,
            bore_m,
            stroke_m,
            conrod_m,
            clearance_m3,
            valve,
            junction_totals,
        )

    def _run_steady(
        self,
        rpm: float,
        pipe_cells: int,
        pipe_length_m: float,
        pipe_diameter_m: float,
        bore_m: float,
        stroke_m: float,
        conrod_m: float,
        clearance_m3: float,
        valve: ValveTiming,
        junction_totals: Optional[Tuple[float, float, float]],
    ) -> Dict[str, List[float]]:
        _, result, _ = self._run_cycles(
            rpm,
            pipe_cells,
            pipe_length_m,
            pipe_diameter_m,
            bore_m,
            stroke_m,
            conrod_m,
            clearance_m3,
            valve,
            junction_totals,
            max_cycles=self.cfg.max_cycles,
            convergence_enabled=True,
            state=None,
            cycle_offset=0,
            sweep_step=None,
            sweep_rpm=None,
            check_finite=False,
            track_pumping_work=self.cfg.enable_pumping_work,
            track_map=False,
        )
        return result

    def _run_sweep(
        self,
        pipe_cells: int,
        pipe_length_m: float,
        pipe_diameter_m: float,
        bore_m: float,
        stroke_m: float,
        conrod_m: float,
        clearance_m3: float,
        valve: ValveTiming,
        junction_totals: Optional[Tuple[float, float, float]],
    ) -> Dict[str, List[float]]:
        sweep_cfg = self.cfg.sweep
        rpm_values = _build_rpm_grid(sweep_cfg)
        disp_m3 = math.pi * (bore_m * 0.5) ** 2 * stroke_m
        base_state = _build_initial_state(self.cfg, pipe_cells, clearance_m3)
        state = _clone_state(base_state, self.cfg)
        throttle_positions_enabled = self.cfg.throttle.enabled and (
            sweep_cfg.throttle_position_grid is not None or sweep_cfg.throttle_position_from_load is not None
        )
        record_part_load_metrics = sweep_cfg.record_part_load_metrics or throttle_positions_enabled
        track_pumping_work = self.cfg.enable_pumping_work or record_part_load_metrics
        track_map = record_part_load_metrics
        throttle_position_original = self.cfg.throttle.position
        combined = {
            "angle_deg": [],
            "pressure": [],
            "ve": [],
            "trapped_mass": [],
            "indicated_work": [],
            "periodicity_metric": [],
            "convergence_history": [],
        }
        if self.cfg.fuel.enabled:
            combined["fuel_metrics"] = []
        sweep_results: List[dict] = []
        cycle_offset = 0
        for step_index, rpm in enumerate(rpm_values):
            if not sweep_cfg.carry_state:
                state = _clone_state(base_state, self.cfg)
            if throttle_positions_enabled:
                pos = _resolve_sweep_throttle_position(sweep_cfg, step_index, len(rpm_values))
                if pos is not None:
                    self.cfg.throttle.position = _clamp_throttle_position(pos)
            try:
                state, step_result, cycles_run = self._run_cycles(
                    rpm,
                    pipe_cells,
                    pipe_length_m,
                    pipe_diameter_m,
                    bore_m,
                    stroke_m,
                    conrod_m,
                    clearance_m3,
                    valve,
                    junction_totals,
                    max_cycles=sweep_cfg.cycles_per_step,
                    convergence_enabled=False,
                    state=state,
                    cycle_offset=cycle_offset,
                    sweep_step=step_index,
                    sweep_rpm=rpm,
                    check_finite=True,
                    track_pumping_work=track_pumping_work,
                    track_map=track_map,
                )
                cycle_offset += cycles_run
            except Exception as exc:  # pragma: no cover - defensive in sweep mode
                step_summary = {
                    "rpm": float(rpm),
                    "imep": None,
                    "torque": None,
                    "power": None,
                    "trapped_mass": None,
                    "ve": None,
                    "periodicity_error": None,
                    "step_index": int(step_index),
                    "cycle_index": None,
                    "time_s": float(step_index * sweep_cfg.seconds_per_step)
                    if sweep_cfg.ramp_mode == "linear_time"
                    else None,
                    "status": "failed",
                    "reason": str(exc),
                }
                if sweep_cfg.record_every_step or step_index == len(rpm_values) - 1:
                    sweep_results.append(step_summary)
                if sweep_cfg.abort_on_fail:
                    break
                state = _clone_state(base_state, self.cfg)
                continue

            for key in combined:
                combined[key].extend(step_result.get(key, []))

            cycle_index = cycle_offset - 1 if cycles_run > 0 else None
            indicated_work = step_result["indicated_work"][-1] if step_result["indicated_work"] else 0.0
            imep = indicated_work / max(disp_m3, 1e-12)
            torque = indicated_work / (2.0 * math.pi)
            omega = rpm * 2.0 * math.pi / 60.0
            power = torque * omega
            trapped_mass = step_result["trapped_mass"][-1] if step_result["trapped_mass"] else 0.0
            ve_value = max(step_result["ve"]) if step_result["ve"] else None
            periodicity_error = step_result["periodicity_metric"][-1] if step_result["periodicity_metric"] else None
            cycles_per_second = rpm / 120.0
            brake_power_w = indicated_work * cycles_per_second
            step_summary = {
                "rpm": float(rpm),
                "imep": float(imep),
                "torque": float(torque),
                "power": float(power),
                "trapped_mass": float(trapped_mass),
                "ve": float(ve_value) if ve_value is not None else None,
                "periodicity_error": float(periodicity_error) if periodicity_error is not None else None,
                "step_index": int(step_index),
                "cycle_index": int(cycle_index) if cycle_index is not None else None,
                "time_s": float(step_index * sweep_cfg.seconds_per_step)
                if sweep_cfg.ramp_mode == "linear_time"
                else None,
                "status": "ok",
            }
            if record_part_load_metrics:
                step_summary["brake_power_w"] = float(brake_power_w)
            if track_pumping_work:
                pump_hist = step_result.get("pumping_work", [])
                if pump_hist:
                    step_summary["pumping_work"] = float(pump_hist[-1])
            if track_map:
                map_hist = step_result.get("map_estimate", [])
                if map_hist:
                    step_summary["map_estimate"] = float(map_hist[-1])
            if self.cfg.fuel.enabled:
                fuel_tail = step_result.get("fuel_metrics", [])
                if fuel_tail:
                    step_summary.update(fuel_tail[-1])
            if sweep_cfg.record_every_step or step_index == len(rpm_values) - 1:
                sweep_results.append(step_summary)

        self.cfg.throttle.position = throttle_position_original
        combined["sweep_results"] = sweep_results
        return combined

    def _run_cycles(
        self,
        rpm: float,
        pipe_cells: int,
        pipe_length_m: float,
        pipe_diameter_m: float,
        bore_m: float,
        stroke_m: float,
        conrod_m: float,
        clearance_m3: float,
        valve: ValveTiming,
        junction_totals: Optional[Tuple[float, float, float]],
        *,
        max_cycles: int,
        convergence_enabled: bool,
        state: Optional[_OrchestratorState],
        cycle_offset: int,
        sweep_step: Optional[int],
        sweep_rpm: Optional[float],
        check_finite: bool,
        track_pumping_work: bool = False,
        track_map: bool = False,
    ) -> tuple[_OrchestratorState, Dict[str, List[float]], int]:
        dx = pipe_length_m / pipe_cells
        area_face = math.pi * (pipe_diameter_m * 0.5) ** 2
        piston_area = math.pi * (bore_m * 0.5) ** 2
        pipe_volume = area_face * pipe_length_m
        if state is None:
            state = _build_initial_state(self.cfg, pipe_cells, clearance_m3)

        U = state.U
        cyl = state.cyl
        rho0 = state.rho0
        p0 = state.p0
        T0 = state.T0
        twall_pipe_k = state.twall_pipe_k
        throttle_pos = state.throttle_pos
        plenum = state.plenum
        plenum_enabled = plenum is not None
        exhaust_plenum = state.exhaust_plenum
        exhaust_plenum_enabled = exhaust_plenum is not None

        angle_history: List[float] = []
        p_history: List[float] = []
        ve_history: List[float] = []
        ve_cycle_history: List[float] = []
        work_history: List[float] = []
        trapped_history: List[float] = []
        periodicity_history: List[float] = []
        convergence_history: List[dict] = []
        fuel_metrics_history: List[dict] = []
        pumping_work_history: List[float] = []
        map_history: List[float] = []

        omega = rpm * 2.0 * math.pi / 60.0
        dt_theta = math.radians(1.0) / max(omega, 1e-9)
        cycle = 0
        cycles_run = 0
        last_trapped = None
        last_work = None
        last_imep = None
        periodicity_count = 0
        disp_m3 = math.pi * (bore_m * 0.5) ** 2 * stroke_m

        while cycle < max_cycles:
            indicated_work = 0.0
            pumping_work = 0.0
            pumping_work_approx = 0.0
            pumping_samples = 0
            map_sum = 0.0
            map_samples = 0
            prev_p = None
            prev_V = None
            prev_angle = None
            U_cycle_start = U.copy()
            prev_down_totals: Optional[Tuple[float, float, float]] = None
            cycle_m_fresh_peak = cyl.m_fresh
            for step in range(int(720.0 / 1.0)):
                angle_deg = step
                theta = math.radians(angle_deg)
                V, dVdtheta = slider_crank_volume(theta, bore_m, stroke_m, conrod_m, clearance_m3)
                cyl.V = V
                dVdt = dVdtheta * omega
                x_piston = max((V - clearance_m3) / max(piston_area, 1e-12), 0.0)
                A_wet = math.pi * bore_m * x_piston + 2.0 * piston_area

                prim_pipe = conserved_to_primitive(U[[1]], self.cfg.gamma, self.cfg.gas_constant)[0]
                p_pipe = prim_pipe[2]
                T_pipe = prim_pipe[3]
                Y_pipe = prim_pipe[4]
                u_pipe = prim_pipe[1]
                rho_pipe = prim_pipe[0]
                if track_map and angle_deg < 180:
                    map_sum += plenum.p if plenum_enabled else p_pipe
                    map_samples += 1
                p0_pipe, T0_pipe = stagnation_from_static(
                    p_pipe,
                    T_pipe,
                    u_pipe,
                    self.cfg.gamma,
                    self.cfg.gas_constant,
                    cp_model=self.cfg.cp_model,
                    Y_fresh=Y_pipe,
                )
                if junction_totals is not None:
                    p0_pipe = float(max(junction_totals[0], 1e-6))
                    T0_pipe = float(max(junction_totals[1], 1e-6))
                    Y_pipe = float(min(max(junction_totals[2], 0.0), 1.0))
                relaxed_totals, _ = _relax_downstream_totals(
                    prev_down_totals,
                    (p0_pipe, T0_pipe, Y_pipe),
                    self.cfg.coupling_relax_alpha,
                    cycle,
                    self.cfg.coupling_relax_warmup_iters,
                )
                prev_down_totals = relaxed_totals
                if self.cfg.pipe_role == "exhaust" and exhaust_plenum_enabled:
                    Y_cyl = cyl.m_fresh / max(cyl.m_total, 1e-9)
                    rho_plenum = exhaust_plenum.p / (
                        self.cfg.gas_constant * max(exhaust_plenum.T, 1e-9)
                    )
                    mdot_valve, Hdot_valve, Ydot_valve, _ = boundary_flux_from_nozzle(
                        cyl.p,
                        cyl.T,
                        Y_cyl,
                        exhaust_plenum.p,
                        valve=valve,
                        angle_deg=angle_deg,
                        gamma=self.cfg.gamma,
                        gas_constant=self.cfg.gas_constant,
                        cp=self.cfg.cp,
                        cp_model=self.cfg.cp_model,
                        p0_down=exhaust_plenum.p,
                        T0_down=exhaust_plenum.T,
                        Y0_down=exhaust_plenum.Y,
                        loss_coeff=self.cfg.loss_coeff,
                        rho_down=rho_plenum,
                        u_down=None,
                        area_pipe_m2=area_face,
                    )

                    plenum_valve = _FixedAreaValve(area_face)
                    mdot_plenum, Hdot_plenum, Ydot_plenum, _ = boundary_flux_from_nozzle(
                        exhaust_plenum.p,
                        exhaust_plenum.T,
                        exhaust_plenum.Y,
                        prim_pipe[2],
                        valve=plenum_valve,
                        angle_deg=0.0,
                        gamma=self.cfg.gamma,
                        gas_constant=self.cfg.gas_constant,
                        cp=self.cfg.cp,
                        cp_model=self.cfg.cp_model,
                        p0_down=relaxed_totals[0],
                        T0_down=relaxed_totals[1],
                        Y0_down=relaxed_totals[2],
                        loss_coeff=0.0,
                        rho_down=rho_pipe,
                        u_down=u_pipe,
                        area_pipe_m2=area_face,
                    )

                    if mdot_plenum >= 0.0:
                        ghost_p = exhaust_plenum.p
                        ghost_T = exhaust_plenum.T
                        ghost_Y = exhaust_plenum.Y
                    else:
                        ghost_p = relaxed_totals[0]
                        ghost_T = relaxed_totals[1]
                        ghost_Y = relaxed_totals[2]
                    ghost = ghost_state_from_nozzle(
                        ghost_p,
                        ghost_T,
                        ghost_Y,
                        mdot_plenum,
                        max(area_face, 1e-9),
                        self.cfg.gamma,
                        self.cfg.gas_constant,
                        phase=self.cfg.coupling_phase,
                        cp_model=self.cfg.cp_model,
                    )

                    exhaust_plenum.update(
                        dt_theta,
                        mdot_valve,
                        Hdot_valve,
                        Ydot_valve,
                        mdot_plenum,
                        Hdot_plenum,
                        Ydot_plenum,
                    )

                    mdot, Hdot, Ydot = mdot_valve, Hdot_valve, Ydot_valve
                else:
                    mdot, Hdot, Ydot, ghost = _compute_valve_boundary(
                        self.cfg,
                        valve,
                        angle_deg,
                        cyl,
                        prim_pipe,
                        relaxed_totals[0],
                        relaxed_totals[1],
                        relaxed_totals[2],
                        area_face,
                        rho_pipe,
                        u_pipe,
                    )

                if mdot >= 0.0:
                    mdot_in = 0.0
                    Hdot_in = 0.0
                    Ydot_in = 0.0
                    mdot_out = mdot
                    Hdot_out = Hdot
                    Ydot_out = Ydot
                else:
                    mdot_in = -mdot
                    Hdot_in = -Hdot
                    Ydot_in = -Ydot
                    mdot_out = 0.0
                    Hdot_out = 0.0
                    Ydot_out = 0.0
                if track_pumping_work:
                    rho_safe = max(rho_pipe, 1e-9)
                    delta_p_in = p_pipe - cyl.p
                    delta_p_out = cyl.p - p_pipe
                    pumping_work_approx += (
                        (mdot_in * delta_p_in + mdot_out * delta_p_out) / rho_safe
                    ) * dt_theta
                Qdot = combustion_qdot(
                    angle_deg,
                    rpm,
                    cyl.m_fresh,
                    cyl.m_total,
                    self.cfg.combustion,
                )
                cyl.update(
                    dt_theta,
                    mdot_in,
                    Hdot_in,
                    Ydot_in,
                    mdot_out,
                    Hdot_out,
                    Ydot_out,
                    Qdot,
                    dVdt,
                    A_wet=A_wet,
                )

                throttle_pos = _update_throttle_position(
                    throttle_pos,
                    self.cfg.throttle.position,
                    dt_theta,
                    self.cfg.throttle.rate_limit_per_s,
                )
                throttle_active = False
                throttle_ghost = None
                plenum_ghost = None
                if self.cfg.pipe_role == "intake" and plenum_enabled:
                    prim_out = conserved_to_primitive(U[[-2]], self.cfg.gamma, self.cfg.gas_constant)[0]
                    p_pipe_out = prim_out[2]
                    T_pipe_out = prim_out[3]
                    Y_pipe_out = prim_out[4]
                    u_pipe_out = prim_out[1]
                    p0_pipe_out, T0_pipe_out = stagnation_from_static(
                        p_pipe_out,
                        T_pipe_out,
                        u_pipe_out,
                        self.cfg.gamma,
                        self.cfg.gas_constant,
                        cp_model=self.cfg.cp_model,
                        Y_fresh=Y_pipe_out,
                    )
                    p0_amb = self.cfg.throttle.p0_amb_Pa if self.cfg.throttle.p0_amb_Pa is not None else p0
                    T0_amb = self.cfg.throttle.T0_amb_K if self.cfg.throttle.T0_amb_K is not None else T0
                    Y0_amb = self.cfg.throttle.Y0_amb if self.cfg.throttle.Y0_amb is not None else 1.0
                    Y0_amb = min(max(float(Y0_amb), 0.0), 1.0)

                    if self.cfg.throttle.enabled:
                        area_eff_throttle = _throttle_area_eff(self.cfg.throttle, throttle_pos)
                    else:
                        area_eff_throttle = area_face

                    mdot_throttle, Hdot_throttle, Ydot_throttle = nozzle_mass_flow(
                        p0_amb,
                        T0_amb,
                        plenum.p,
                        area_eff_throttle,
                        self.cfg.gamma,
                        self.cfg.gas_constant,
                        self.cfg.cp,
                        Y0_amb,
                        p0_down=plenum.p,
                        T0_down=plenum.T,
                        Y0_down=plenum.Y,
                        cp_model=self.cfg.cp_model,
                    )

                    mdot_plenum, Hdot_plenum, Ydot_plenum = nozzle_mass_flow(
                        plenum.p,
                        plenum.T,
                        p_pipe_out,
                        area_face,
                        self.cfg.gamma,
                        self.cfg.gas_constant,
                        self.cfg.cp,
                        plenum.Y,
                        p0_down=p0_pipe_out,
                        T0_down=T0_pipe_out,
                        Y0_down=Y_pipe_out,
                        cp_model=self.cfg.cp_model,
                    )

                    if mdot_plenum >= 0.0:
                        ghost_p0 = plenum.p
                        ghost_T0 = plenum.T
                        ghost_Y0 = plenum.Y
                    else:
                        ghost_p0 = p0_pipe_out
                        ghost_T0 = T0_pipe_out
                        ghost_Y0 = Y_pipe_out
                    plenum_ghost = ghost_state_from_nozzle(
                        ghost_p0,
                        ghost_T0,
                        ghost_Y0,
                        mdot_plenum,
                        max(area_face, 1e-9),
                        self.cfg.gamma,
                        self.cfg.gas_constant,
                        phase=self.cfg.coupling_phase,
                        cp_model=self.cfg.cp_model,
                    )
                    plenum.update(
                        dt_theta,
                        mdot_throttle,
                        Hdot_throttle,
                        Ydot_throttle,
                        mdot_plenum,
                        Hdot_plenum,
                        Ydot_plenum,
                    )
                    throttle_active = True
                else:
                    throttle_active = self.cfg.pipe_role == "intake" and _throttle_is_active(
                        self.cfg.throttle,
                        throttle_pos,
                    )
                    if throttle_active:
                        area_eff_throttle = _throttle_area_eff(self.cfg.throttle, throttle_pos)
                        prim_out = conserved_to_primitive(U[[-2]], self.cfg.gamma, self.cfg.gas_constant)[0]
                        p_pipe_out = prim_out[2]
                        T_pipe_out = prim_out[3]
                        Y_pipe_out = prim_out[4]
                        u_pipe_out = prim_out[1]
                        p0_pipe_out, T0_pipe_out = stagnation_from_static(
                            p_pipe_out,
                            T_pipe_out,
                            u_pipe_out,
                            self.cfg.gamma,
                            self.cfg.gas_constant,
                            cp_model=self.cfg.cp_model,
                            Y_fresh=Y_pipe_out,
                        )
                        p0_amb = self.cfg.throttle.p0_amb_Pa if self.cfg.throttle.p0_amb_Pa is not None else p0
                        T0_amb = self.cfg.throttle.T0_amb_K if self.cfg.throttle.T0_amb_K is not None else T0
                        Y0_amb = self.cfg.throttle.Y0_amb if self.cfg.throttle.Y0_amb is not None else 1.0
                        Y0_amb = min(max(float(Y0_amb), 0.0), 1.0)

                        if area_eff_throttle <= 0.0:
                            throttle_ghost = U[-2].copy()
                            throttle_ghost[1] = -throttle_ghost[1]
                        else:
                            mdot_throttle, _, _ = nozzle_mass_flow(
                                p0_amb,
                                T0_amb,
                                p_pipe_out,
                                area_eff_throttle,
                                self.cfg.gamma,
                                self.cfg.gas_constant,
                                self.cfg.cp,
                                Y0_amb,
                                p0_down=p0_pipe_out,
                                T0_down=T0_pipe_out,
                                Y0_down=Y_pipe_out,
                                cp_model=self.cfg.cp_model,
                            )
                            if mdot_throttle >= 0.0:
                                thr_p = p0_amb
                                thr_T = T0_amb
                                thr_Y = Y0_amb
                            else:
                                thr_p = p0_pipe_out
                                thr_T = T0_pipe_out
                                thr_Y = Y_pipe_out
                            throttle_ghost = ghost_state_from_nozzle(
                                thr_p,
                                thr_T,
                                thr_Y,
                                mdot_throttle,
                                max(area_face, 1e-9),
                                self.cfg.gamma,
                                self.cfg.gas_constant,
                                phase=self.cfg.coupling_phase,
                                cp_model=self.cfg.cp_model,
                            )

                t_elapsed = 0.0
                if throttle_active:
                    p_outlet = None
                    outlet_mode = "copy"
                elif self.cfg.outlet_mode == "copy":
                    p_outlet = None
                    outlet_mode = self.cfg.outlet_mode
                else:
                    p_outlet = self.cfg.p_outlet if self.cfg.p_outlet is not None else p0
                    outlet_mode = self.cfg.outlet_mode
                dt_cfl_est = cfl_dt(
                    U,
                    dx,
                    self.cfg.gamma,
                    self.cfg.gas_constant,
                    self.cfg.cfl,
                    self.cfg.dt_max,
                    ghost_left=1,
                    ghost_right=1,
                )
                max_substeps = max(
                    10,
                    int(math.ceil(dt_theta / max(self.cfg.dt_max, 1e-12))) * 10,
                )
                max_substeps = max(
                    max_substeps,
                    int(math.ceil(dt_theta / max(dt_cfl_est, 1e-12))) + 5,
                )
                for _ in range(max_substeps):
                    if t_elapsed >= dt_theta:
                        break
                    U[0] = ghost
                    if throttle_active:
                        if plenum_ghost is not None:
                            U[-1] = plenum_ghost
                        elif throttle_ghost is not None:
                            U[-1] = throttle_ghost
                        else:
                            U[-1] = U[-2]
                    else:
                        U[-1] = U[-2]
                    dt_cfl = cfl_dt(
                        U,
                        dx,
                        self.cfg.gamma,
                        self.cfg.gas_constant,
                        self.cfg.cfl,
                        self.cfg.dt_max,
                        ghost_left=1,
                        ghost_right=1,
                    )
                    dt_base = min(dt_cfl, dt_theta - t_elapsed)
                    dt_step, n_substeps = shock_cfl_plan(
                        U,
                        dt_base,
                        self.cfg.gamma,
                        self.cfg.gas_constant,
                        self.cfg.shock_cfl,
                        ghost_left=1,
                        ghost_right=1,
                    )
                    if not math.isfinite(dt_step) or dt_step <= 0.0:
                        raise RuntimeError(
                            "Orchestrator time step stalled: "
                            f"dt_step={dt_step} dt_cfl={dt_cfl} dt_theta={dt_theta} "
                            f"t_elapsed={t_elapsed} rpm={rpm} pipe_cells={pipe_cells} "
                            f"pipe_length_m={pipe_length_m} pipe_diameter_m={pipe_diameter_m}"
                        )
                    dt_sub = dt_step / max(n_substeps, 1)
                    for _ in range(n_substeps):
                        U = muscl_hancock_step(
                            U,
                            dx,
                            dt_sub,
                            self.cfg.gamma,
                            self.cfg.gas_constant,
                            friction_factor=0.0,
                            diameter=pipe_diameter_m,
                            p_outlet=p_outlet,
                            outlet_mode=outlet_mode,
                            reflection_coeff=self.cfg.outlet_reflection,
                            impedance=self.cfg.outlet_impedance,
                            friction_model=self.cfg.friction_model if self.cfg.enable_friction else None,
                            friction_energy_mode=self.cfg.friction_energy_mode,
                            roughness=self.cfg.roughness_m,
                            mu=self.cfg.mu,
                            use_numba_1d=self.cfg.use_numba_1d,
                        )
                        if self.cfg.wall_thermal.enabled:
                            twall_pipe_k = _apply_pipe_wall_thermal(
                                U,
                                dt_sub,
                                self.cfg.wall_thermal,
                                twall_pipe_k,
                                pipe_volume,
                                self.cfg.gamma,
                                self.cfg.gas_constant,
                            )
                    t_elapsed += dt_step
                if t_elapsed < dt_theta:
                    raise RuntimeError(
                        "Orchestrator substep loop exceeded max iterations: "
                        f"max_substeps={max_substeps} t_elapsed={t_elapsed} "
                        f"dt_theta={dt_theta} rpm={rpm} pipe_cells={pipe_cells} "
                        f"pipe_length_m={pipe_length_m} pipe_diameter_m={pipe_diameter_m}"
                    )

                angle_history.append(angle_deg + (cycle_offset + cycle) * 720.0)
                p_history.append(cyl.p)
                ve_history.append(cyl.m_fresh / max(rho0 * (math.pi * (bore_m * 0.5) ** 2) * stroke_m, 1e-9))
                if cyl.m_fresh > cycle_m_fresh_peak:
                    cycle_m_fresh_peak = cyl.m_fresh
                if prev_p is not None and prev_V is not None:
                    work_step = 0.5 * (prev_p + cyl.p) * (V - prev_V)
                    indicated_work += work_step
                    if track_pumping_work and prev_angle is not None:
                        if prev_angle < 180 or prev_angle >= 540:
                            pumping_work += work_step
                            pumping_samples += 1
                prev_p = cyl.p
                prev_V = V
                prev_angle = angle_deg

            trapped_history.append(cyl.m_fresh)
            ve_cycle_history.append(
                cycle_m_fresh_peak / max(rho0 * (math.pi * (bore_m * 0.5) ** 2) * stroke_m, 1e-9)
            )
            work_history.append(indicated_work)
            if track_pumping_work:
                if pumping_samples > 0:
                    pumping_work_history.append(pumping_work)
                else:
                    pumping_work_history.append(pumping_work_approx)
            if track_map:
                map_history.append(map_sum / map_samples if map_samples > 0 else 0.0)
            denom = max(np.linalg.norm(U_cycle_start[1:-1]), 1e-12)
            periodicity_metric = float(np.linalg.norm(U[1:-1] - U_cycle_start[1:-1]) / denom)
            periodicity_history.append(periodicity_metric)
            imep = indicated_work / max(disp_m3, 1e-12)
            if self.cfg.fuel.enabled:
                m_air_fresh = cyl.fresh_air_mass()
                fuel_metrics_history.append(
                    _compute_fuel_metrics(
                        m_air_fresh,
                        rpm,
                        indicated_work,
                        self.cfg.fuel,
                    )
                )
            if last_trapped is None:
                err_trapped = 0.0
            else:
                err_trapped = abs(trapped_history[-1] - last_trapped) / max(abs(last_trapped), 1e-9)
            if last_imep is None:
                err_imep = 0.0
            else:
                err_imep = abs(imep - last_imep) / max(abs(last_imep), 1e-9)
            entry = {
                "k": int(cycle_offset + cycle),
                "err_trapped_mass": float(err_trapped),
                "err_imep": float(err_imep),
                "err_periodicity_1d": float(periodicity_metric),
            }
            if sweep_step is not None:
                entry["sweep_step"] = int(sweep_step)
                entry["sweep_rpm"] = float(sweep_rpm) if sweep_rpm is not None else None
                entry["sweep_cycle"] = int(cycle)
            convergence_history.append(entry)
            if periodicity_metric < self.cfg.periodicity_tol:
                periodicity_count += 1
            else:
                periodicity_count = 0

            cycles_run += 1
            if check_finite and not _state_is_finite(U, cyl):
                raise ValueError("Non-finite state detected during sweep step")

            if convergence_enabled and last_trapped is not None and last_work is not None:
                cv_ok = (
                    abs(trapped_history[-1] - last_trapped) / max(last_trapped, 1e-9) < self.cfg.convergence_tol
                    and abs(work_history[-1] - last_work) / max(abs(last_work), 1e-9) < self.cfg.convergence_tol
                )
                if cv_ok and periodicity_count >= self.cfg.periodicity_required:
                    break
            last_trapped = trapped_history[-1]
            last_work = work_history[-1]
            last_imep = imep
            cycle += 1

        state.U = U
        state.cyl = cyl
        state.twall_pipe_k = twall_pipe_k
        state.throttle_pos = throttle_pos
        state.plenum = plenum
        state.exhaust_plenum = exhaust_plenum
        result = {
            "angle_deg": angle_history,
            "pressure": p_history,
            "ve": ve_history,
            "ve_cycle": ve_cycle_history,
            "trapped_mass": trapped_history,
            "indicated_work": work_history,
            "periodicity_metric": periodicity_history,
            "convergence_history": convergence_history,
        }
        if track_pumping_work:
            result["pumping_work"] = pumping_work_history
        if track_map:
            result["map_estimate"] = map_history
        if self.cfg.fuel.enabled:
            result["fuel_metrics"] = fuel_metrics_history
        return state, result, cycles_run


def _build_valve_timing(engine: Engine, pipe_role: str) -> ValveTiming:
    cam = engine.camshaft
    head = engine.head
    if pipe_role == "intake":
        lift_m = float(cam.intake_lift) * 1e-3
        seat_mm = head.intake_valve_diameter_mm
        legacy_mm = head.intake_valve_diameter
        if seat_mm is None and legacy_mm is not None:
            seat_mm = legacy_mm
        if seat_mm is None:
            seat_mm = 35.0
        open_start = 0.0
        open_end = open_start + max(float(cam.intake_duration), 1.0)
        cd = 0.9
    else:
        lift_m = float(cam.exhaust_lift) * 1e-3
        seat_mm = head.exhaust_valve_seat_diameter_mm
        fallback_mm = head.exhaust_valve_diameter_mm
        legacy_mm = head.exhaust_valve_diameter
        if seat_mm is None:
            seat_mm = fallback_mm
        if seat_mm is None and legacy_mm is not None:
            seat_mm = legacy_mm
        if seat_mm is None:
            seat_mm = 30.0
        open_start = 360.0
        open_end = open_start + max(float(cam.exhaust_duration), 1.0)
        cd = float(getattr(engine.simulation_settings, "exhaust_valve_cd", getattr(head, "exhaust_valve_cd", 0.9)))
    return ValveTiming(
        open_start_deg=open_start,
        open_end_deg=open_end,
        max_lift_m=lift_m,
        seat_diameter_m=float(seat_mm) * 1e-3,
        cd=cd,
    )


def _fmep_from_engine(engine: Engine, rpm: float) -> float:
    f_cfg = engine.friction
    f_base = getattr(f_cfg, "friction_base_kpa", 35.0) + 5.0
    f_lin = getattr(f_cfg, "friction_linear_factor", 0.02)
    f_quad = getattr(f_cfg, "friction_quadratic_factor", 1.8e-6)
    fmep_kpa = f_base + f_lin * rpm + f_quad * rpm * rpm
    be_type = (getattr(f_cfg, "bottom_end_type", "Standard") or "Standard").lower()
    if be_type == "performance":
        fmep_kpa *= 0.85
    elif be_type == "race":
        fmep_kpa *= 0.65
    else:
        fmep_kpa *= 1.05
    fmep_pa = fmep_kpa * 1000.0
    fmep_pa *= getattr(f_cfg, "global_scaling_factor", 1.0)
    return float(fmep_pa)


def _resolve_fmep_pa(project_config: dict, engine: Engine, rpm: float) -> float:
    brake_model = project_config.get("brake_model", {})
    if "fmep_pa" in brake_model:
        return float(brake_model.get("fmep_pa", 0.0))
    if "fmep_curve_scale" in brake_model:
        scale = float(brake_model.get("fmep_curve_scale", 1.0))
        return max(_fmep_from_engine(engine, rpm) * scale, 0.0)
    return 0.0


def run_advanced_single_point(
    project_config: dict,
    rpm: float,
    *,
    cycles: int = 3,
    warm_start_state: Optional[dict] = None,
) -> tuple[dict, dict]:
    engine = Engine.from_dict(project_config)
    calibration_cfg = project_config.get("calibration", {})
    pipe_role = calibration_cfg.get("pipe_role", "intake")
    if pipe_role not in ("intake", "exhaust"):
        raise ValueError("calibration.pipe_role must be 'intake' or 'exhaust'")

    if pipe_role == "intake":
        pipe_length_m = engine.intake.runner_length * 1e-3
        pipe_diameter_m = engine.intake.runner_diameter * 1e-3
        gamma = engine.simulation_settings.gamma_air
    else:
        pipe_length_m = engine.exhaust.header_primary_length * 1e-3
        pipe_diameter_m = engine.exhaust.header_primary_diameter * 1e-3
        gamma = engine.simulation_settings.gamma_exhaust

    bore_m = engine.block.bore * 1e-3
    stroke_m = engine.block.stroke * 1e-3
    conrod_m = engine.block.conrod_length * 1e-3
    area = math.pi * (bore_m * 0.5) ** 2
    clearance_m3 = area * stroke_m / max(engine.head.compression_ratio - 1.0, 1e-6)

    prefill_cfg = project_config.get("pipe_prefill", {})
    amb_p_pa = float(engine.simulation_settings.air_pressure_bar) * 100000.0
    amb_T_k = float(engine.simulation_settings.air_temperature_c) + 273.15
    exhaust_prefill_T = prefill_cfg.get("exhaust_prefill_T_K", prefill_cfg.get("exhaust_prefill_T", 700.0))
    pipe_prefill = PipePrefillConfig(
        enabled=bool(prefill_cfg.get("enabled", False)),
        auto=bool(prefill_cfg.get("auto", False)),
        auto_amb_p_Pa=float(prefill_cfg.get("auto_amb_p_Pa", amb_p_pa)),
        auto_amb_T_K=float(prefill_cfg.get("auto_amb_T_K", amb_T_k)),
        exhaust_prefill_T_K=float(exhaust_prefill_T),
        intake=PipePrefillState(**prefill_cfg.get("intake", {})),
        exhaust=PipePrefillState(**prefill_cfg.get("exhaust", {})),
    )
    wall_bc = ValveClosedWallBCConfig(**project_config.get("valve_closed_wall_bc", {}))
    sim_plenum = getattr(engine.simulation_settings, "intake_plenum", {})
    sim_exhaust_plenum = getattr(engine.simulation_settings, "exhaust_plenum", {})
    plenum_cfg = IntakePlenumConfig.from_dict(sim_plenum or project_config.get("intake_plenum", {}))
    exhaust_plenum_cfg = ExhaustPlenumConfig.from_dict(
        sim_exhaust_plenum or project_config.get("exhaust_plenum", {})
    )
    sim_shock_cfl = getattr(engine.simulation_settings, "shock_cfl", {})
    shock_cfl_cfg = ShockCFLConfig.from_dict(sim_shock_cfl or project_config.get("shock_cfl", {}))

    cfg = OrchestratorConfig(
        gamma=float(gamma),
        gas_constant=float(engine.simulation_settings.gas_constant_R),
        cp_model=engine.simulation_settings.cp_model,
        cfl=float(calibration_cfg.get("cfl", 0.5)),
        dt_max=float(calibration_cfg.get("dt_max", 5e-5)),
        max_cycles=int(cycles),
        convergence_tol=0.0,
        periodicity_tol=0.0,
        periodicity_required=int(cycles) + 1,
        pipe_role=pipe_role,
        throttle=engine.throttle,
        pipe_prefill=pipe_prefill,
        valve_closed_wall_bc=wall_bc,
        fuel=engine.simulation_settings.fuel,
        wall_thermal=engine.simulation_settings.wall_thermal,
        intake_plenum=plenum_cfg,
        exhaust_plenum=exhaust_plenum_cfg,
        shock_cfl=shock_cfl_cfg,
    )
    orchestrator = Orchestrator(cfg)

    warm_state = warm_start_state or {}
    state = warm_state.get("state")
    cycle_offset = int(warm_state.get("cycle_offset", 0))
    valve = _build_valve_timing(engine, pipe_role)
    state, result, cycles_run = orchestrator._run_cycles(
        rpm=float(rpm),
        pipe_cells=int(calibration_cfg.get("pipe_cells", 1)),
        pipe_length_m=pipe_length_m,
        pipe_diameter_m=pipe_diameter_m,
        bore_m=bore_m,
        stroke_m=stroke_m,
        conrod_m=conrod_m,
        clearance_m3=clearance_m3,
        valve=valve,
        junction_totals=None,
        max_cycles=int(cycles),
        convergence_enabled=False,
        state=state,
        cycle_offset=cycle_offset,
        sweep_step=None,
        sweep_rpm=None,
        check_finite=True,
    )
    next_state = {"state": state, "cycle_offset": cycle_offset + cycles_run}

    indicated_work = result["indicated_work"][-1] if result["indicated_work"] else 0.0
    disp_per_cyl_m3 = area * stroke_m
    disp_total_m3 = disp_per_cyl_m3 * engine.block.num_cylinders
    indicated_work_total = indicated_work * engine.block.num_cylinders
    indicated_torque_nm = indicated_work_total / (2.0 * math.pi)
    omega = float(rpm) * 2.0 * math.pi / 60.0
    indicated_power_w = indicated_torque_nm * omega

    fmep_pa = _resolve_fmep_pa(project_config, engine, float(rpm))
    friction_torque = fmep_pa * disp_total_m3 / (4.0 * math.pi)
    brake_torque_nm = max(0.0, indicated_torque_nm - friction_torque)
    brake_power_w = brake_torque_nm * omega
    imep_pa = indicated_work / max(disp_per_cyl_m3, 1e-12)
    bmep_pa = brake_torque_nm * 4.0 * math.pi / max(disp_total_m3, 1e-12)

    ve_value = max(result.get("ve", []), default=0.0)
    trapped = result["trapped_mass"][-1] if result["trapped_mass"] else 0.0
    fuel_flow_total = None
    bsfc = None
    eta_bte = None
    eta_ite = None
    if cfg.fuel.enabled and result.get("fuel_metrics"):
        fuel_last = result["fuel_metrics"][-1]
        afr_used = fuel_last.get("afr_used")
        m_air_fresh = fuel_last.get("m_air_fresh_per_cycle_kg", 0.0)
        m_fuel_per_cycle = m_air_fresh / max(float(afr_used or 0.0), 1e-12)
        cycles_per_second = float(rpm) / 120.0
        fuel_flow_total = m_fuel_per_cycle * cycles_per_second * engine.block.num_cylinders
        fuel_power = fuel_flow_total * cfg.fuel.lhv_j_per_kg * cfg.fuel.eta_comb
        bsfc = _bsfc_g_per_kwh(fuel_flow_total, brake_power_w)
        if fuel_power > 0.0:
            eta_bte = brake_power_w / fuel_power
            eta_ite = indicated_power_w / fuel_power

    out = {
        "rpm": float(rpm),
        "imep_pa": float(imep_pa),
        "bmep_pa": float(bmep_pa),
        "indicated_torque_nm": float(indicated_torque_nm),
        "indicated_power_w": float(indicated_power_w),
        "brake_torque_nm": float(brake_torque_nm),
        "brake_power_w": float(brake_power_w),
        "trapped_mass": float(trapped),
        "ve": float(ve_value),
        "fuel_flow_kg_s": float(fuel_flow_total) if fuel_flow_total is not None else None,
        "bsfc_g_per_kwh": float(bsfc) if bsfc is not None else None,
        "eta_bte": float(eta_bte) if eta_bte is not None else None,
        "eta_ite": float(eta_ite) if eta_ite is not None else None,
        "raw": result,
    }
    return out, next_state
