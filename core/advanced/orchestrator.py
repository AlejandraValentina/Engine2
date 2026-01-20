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
from core.advanced.state import Primitive1D, primitive_to_conserved, stagnation_from_static
from core.advanced.solver_1d import cfl_dt, conserved_to_primitive, muscl_hancock_step
from core.advanced.nozzle import nozzle_mass_flow
from core.engine_components import Engine, FuelConfig, Throttle

try:
    from core.advanced.solver_1d import reset_guard_counters
except ImportError:  # pragma: no cover - compat for older solver_1d
    def reset_guard_counters() -> None:
        return None


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
    sweep: SweepConfig = field(default_factory=SweepConfig)
    fuel: FuelConfig = field(default_factory=FuelConfig)

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
        if self.throttle.enabled:
            if self.throttle.body_diam_m <= 0.0:
                raise ValueError("throttle.body_diam_m must be positive when enabled")
            if self.throttle.area_exponent <= 0.0:
                raise ValueError("throttle.area_exponent must be positive when enabled")
            if self.throttle.cd <= 0.0:
                raise ValueError("throttle.cd must be positive when enabled")
        if self.pipe_prefill.enabled:
            _validate_prefill_state(self.pipe_prefill.intake, "pipe_prefill.intake")
            _validate_prefill_state(self.pipe_prefill.exhaust, "pipe_prefill.exhaust")
        if self.valve_closed_wall_bc.enabled and self.valve_closed_wall_bc.area_eps_m2 <= 0.0:
            raise ValueError("valve_closed_wall_bc.area_eps_m2 must be positive when enabled")
        if self.sweep.enabled:
            if self.sweep.ramp_mode not in ("step", "linear_time"):
                raise ValueError("sweep.ramp_mode must be 'step' or 'linear_time'")
            if self.sweep.rpm_step <= 0.0:
                raise ValueError("sweep.rpm_step must be positive")
            if self.sweep.cycles_per_step < 1:
                raise ValueError("sweep.cycles_per_step must be >= 1")
            if self.sweep.ramp_mode == "linear_time" and self.sweep.seconds_per_step <= 0.0:
                raise ValueError("sweep.seconds_per_step must be positive for linear_time")
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


def _validate_prefill_state(state: PipePrefillState, label: str) -> None:
    if state.p_Pa <= 0.0:
        raise ValueError(f"{label}.p_Pa must be positive")
    if state.T_K <= 0.0:
        raise ValueError(f"{label}.T_K must be positive")
    if not (0.0 <= state.Y <= 1.0):
        raise ValueError(f"{label}.Y must be within [0, 1]")


def _init_pipe_state(
    cfg: OrchestratorConfig, pipe_cells: int
) -> tuple[np.ndarray, float, float, float, float]:
    if cfg.pipe_prefill.enabled:
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
    return _OrchestratorState(U=U, cyl=cyl, rho0=rho0, p0=p0, T0=T0, Y_init=Y_init)


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
    return _OrchestratorState(
        U=state.U.copy(),
        cyl=cyl,
        rho0=state.rho0,
        p0=state.p0,
        T0=state.T0,
        Y_init=state.Y_init,
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


def _throttle_is_active(throttle: Throttle) -> bool:
    if not throttle.enabled:
        return False
    pos = min(max(throttle.position, 0.0), 1.0)
    return pos < 1.0


def _throttle_area_eff(throttle: Throttle) -> float:
    if throttle.body_diam_m <= 0.0:
        raise ValueError("throttle.body_diam_m must be positive when enabled")
    pos = min(max(throttle.position, 0.0), 1.0)
    area_max = math.pi * (throttle.body_diam_m * 0.5) ** 2
    return throttle.cd * area_max * (pos ** throttle.area_exponent)


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
            if self.cfg.fuel.enabled:
                fuel_tail = step_result.get("fuel_metrics", [])
                if fuel_tail:
                    step_summary.update(fuel_tail[-1])
            if sweep_cfg.record_every_step or step_index == len(rpm_values) - 1:
                sweep_results.append(step_summary)

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
    ) -> tuple[_OrchestratorState, Dict[str, List[float]], int]:
        dx = pipe_length_m / pipe_cells
        area_face = math.pi * (pipe_diameter_m * 0.5) ** 2
        piston_area = math.pi * (bore_m * 0.5) ** 2
        if state is None:
            state = _build_initial_state(self.cfg, pipe_cells, clearance_m3)

        U = state.U
        cyl = state.cyl
        rho0 = state.rho0
        p0 = state.p0
        T0 = state.T0

        angle_history: List[float] = []
        p_history: List[float] = []
        ve_history: List[float] = []
        work_history: List[float] = []
        trapped_history: List[float] = []
        periodicity_history: List[float] = []
        convergence_history: List[dict] = []
        fuel_metrics_history: List[dict] = []

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
            prev_p = None
            prev_V = None
            U_cycle_start = U.copy()
            prev_down_totals: Optional[Tuple[float, float, float]] = None
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

                throttle_active = self.cfg.pipe_role == "intake" and _throttle_is_active(self.cfg.throttle)
                throttle_ghost = None
                if throttle_active:
                    area_eff_throttle = _throttle_area_eff(self.cfg.throttle)
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
                while t_elapsed < dt_theta:
                    U[0] = ghost
                    if throttle_active and throttle_ghost is not None:
                        U[-1] = throttle_ghost
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
                    dt_step = min(dt_cfl, dt_theta - t_elapsed)
                    U = muscl_hancock_step(
                        U,
                        dx,
                        dt_step,
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
                    t_elapsed += dt_step

                angle_history.append(angle_deg + (cycle_offset + cycle) * 720.0)
                p_history.append(cyl.p)
                ve_history.append(cyl.m_fresh / max(rho0 * (math.pi * (bore_m * 0.5) ** 2) * stroke_m, 1e-9))
                if prev_p is not None and prev_V is not None:
                    indicated_work += 0.5 * (prev_p + cyl.p) * (V - prev_V)
                prev_p = cyl.p
                prev_V = V

            trapped_history.append(cyl.m_fresh)
            work_history.append(indicated_work)
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
        result = {
            "angle_deg": angle_history,
            "pressure": p_history,
            "ve": ve_history,
            "trapped_mass": trapped_history,
            "indicated_work": work_history,
            "periodicity_metric": periodicity_history,
            "convergence_history": convergence_history,
        }
        if self.cfg.fuel.enabled:
            result["fuel_metrics"] = fuel_metrics_history
        return state, result, cycles_run


def _build_valve_timing(engine: Engine, pipe_role: str) -> ValveTiming:
    cam = engine.camshaft
    head = engine.head
    if pipe_role == "intake":
        lift_m = float(cam.intake_lift) * 1e-3
        seat_mm = head.intake_valve_diameter_mm or head.intake_valve_diameter
        open_start = 0.0
        open_end = open_start + max(float(cam.intake_duration), 1.0)
        cd = 0.9
    else:
        lift_m = float(cam.exhaust_lift) * 1e-3
        seat_mm = head.exhaust_valve_seat_diameter_mm or head.exhaust_valve_diameter_mm or head.exhaust_valve_diameter
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
        fmep_kpa *= 0.9
    elif be_type == "race":
        fmep_kpa *= 0.72
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
    pipe_prefill = PipePrefillConfig(
        enabled=bool(prefill_cfg.get("enabled", False)),
        intake=PipePrefillState(**prefill_cfg.get("intake", {})),
        exhaust=PipePrefillState(**prefill_cfg.get("exhaust", {})),
    )
    wall_bc = ValveClosedWallBCConfig(**project_config.get("valve_closed_wall_bc", {}))

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
