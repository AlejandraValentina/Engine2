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
from core.advanced.cylinder_cv import CylinderControlVolume, slider_crank_volume
from core.advanced.state import stagnation_from_static
from core.advanced.solver_1d import cfl_dt, conserved_to_primitive, muscl_hancock_step

try:
    from core.advanced.solver_1d import reset_guard_counters
except ImportError:  # pragma: no cover - compat for older solver_1d
    def reset_guard_counters() -> None:
        return None


@dataclass
class OrchestratorConfig:
    gamma: float = 1.35
    gas_constant: float = 287.0
    cp: Optional[float] = None
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
    ) -> Dict[str, List[float]]:
        reset_guard_counters()
        reset_ghost_counters()
        dx = pipe_length_m / pipe_cells
        area_face = math.pi * (pipe_diameter_m * 0.5) ** 2
        rho0 = 1.2
        u0 = 0.0
        p0 = 101325.0
        T0 = p0 / (rho0 * self.cfg.gas_constant)
        E0 = self.cfg.gas_constant * T0 / (self.cfg.gamma - 1.0)
        if self.cfg.initial_Y is not None:
            Y_init = self.cfg.initial_Y
        else:
            Y_init = 0.0 if self.cfg.pipe_role == "exhaust" else 1.0
        if not (0.0 <= Y_init <= 1.0):
            raise ValueError("initial_Y must be within [0, 1]")
        U = np.zeros((pipe_cells + 2, 4))
        U[1:-1, 0] = rho0
        U[1:-1, 1] = rho0 * u0
        U[1:-1, 2] = rho0 * (E0 + 0.5 * u0 * u0)
        U[1:-1, 3] = rho0 * Y_init
        U[0] = U[1]
        U[-1] = U[-2]

        cyl = CylinderControlVolume(
            m_total=rho0 * clearance_m3,
            m_fresh=rho0 * clearance_m3,
            T=T0,
            p=p0,
            V=clearance_m3,
            gamma=self.cfg.gamma,
            gas_constant=self.cfg.gas_constant,
        )

        angle_history: List[float] = []
        p_history: List[float] = []
        ve_history: List[float] = []
        work_history: List[float] = []
        trapped_history: List[float] = []
        periodicity_history: List[float] = []
        convergence_history: List[dict] = []

        omega = rpm * 2.0 * math.pi / 60.0
        dt_theta = math.radians(1.0) / max(omega, 1e-9)
        cycle = 0
        last_trapped = None
        last_work = None
        last_imep = None
        periodicity_count = 0
        disp_m3 = math.pi * (bore_m * 0.5) ** 2 * stroke_m

        while cycle < self.cfg.max_cycles:
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

                prim_pipe = conserved_to_primitive(U[[1]], self.cfg.gamma, self.cfg.gas_constant)[0]
                p_pipe = prim_pipe[2]
                T_pipe = prim_pipe[3]
                Y_pipe = prim_pipe[4]
                u_pipe = prim_pipe[1]
                rho_pipe = prim_pipe[0]
                p0_pipe, T0_pipe = stagnation_from_static(
                    p_pipe, T_pipe, u_pipe, self.cfg.gamma, self.cfg.gas_constant
                )
                Y_cyl = cyl.m_fresh / max(cyl.m_total, 1e-9)
                relaxed_totals, _ = _relax_downstream_totals(
                    prev_down_totals,
                    (p0_pipe, T0_pipe, Y_pipe),
                    self.cfg.coupling_relax_alpha,
                    cycle,
                    self.cfg.coupling_relax_warmup_iters,
                )
                prev_down_totals = relaxed_totals
                mdot, Hdot, Ydot, _ = boundary_flux_from_nozzle(
                    cyl.p,
                    cyl.T,
                    Y_cyl,
                    p_pipe,
                    valve=valve,
                    angle_deg=angle_deg,
                    gamma=self.cfg.gamma,
                    gas_constant=self.cfg.gas_constant,
                    cp=self.cfg.cp,
                    p0_down=relaxed_totals[0],
                    T0_down=relaxed_totals[1],
                    Y0_down=relaxed_totals[2],
                    loss_coeff=self.cfg.loss_coeff,
                    rho_down=rho_pipe,
                    u_down=u_pipe,
                    area_pipe_m2=area_face,
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
                cyl.update(dt_theta, mdot_in, Hdot_in, Ydot_in, mdot_out, Hdot_out, Ydot_out, Qdot, dVdt)

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
                    self.cfg.gamma,
                    self.cfg.gas_constant,
                    phase=self.cfg.coupling_phase,
                )
                t_elapsed = 0.0
                if self.cfg.outlet_mode == "copy":
                    p_outlet = None
                else:
                    p_outlet = self.cfg.p_outlet if self.cfg.p_outlet is not None else p0
                while t_elapsed < dt_theta:
                    U[0] = ghost
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
                        outlet_mode=self.cfg.outlet_mode,
                        reflection_coeff=self.cfg.outlet_reflection,
                        impedance=self.cfg.outlet_impedance,
                        friction_model=self.cfg.friction_model if self.cfg.enable_friction else None,
                        friction_energy_mode=self.cfg.friction_energy_mode,
                        roughness=self.cfg.roughness_m,
                        mu=self.cfg.mu,
                    )
                    t_elapsed += dt_step

                angle_history.append(angle_deg + cycle * 720.0)
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
            if last_trapped is None:
                err_trapped = 0.0
            else:
                err_trapped = abs(trapped_history[-1] - last_trapped) / max(abs(last_trapped), 1e-9)
            if last_imep is None:
                err_imep = 0.0
            else:
                err_imep = abs(imep - last_imep) / max(abs(last_imep), 1e-9)
            convergence_history.append(
                {
                    "k": int(cycle),
                    "err_trapped_mass": float(err_trapped),
                    "err_imep": float(err_imep),
                    "err_periodicity_1d": float(periodicity_metric),
                }
            )
            if periodicity_metric < self.cfg.periodicity_tol:
                periodicity_count += 1
            else:
                periodicity_count = 0

            if last_trapped is not None and last_work is not None:
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

        return {
            "angle_deg": angle_history,
            "pressure": p_history,
            "ve": ve_history,
            "trapped_mass": trapped_history,
            "indicated_work": work_history,
            "periodicity_metric": periodicity_history,
            "convergence_history": convergence_history,
        }
