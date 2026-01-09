from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from core.advanced.coupling import (
    ValveTiming,
    boundary_flux_from_nozzle,
    ghost_state_from_nozzle,
    reset_ghost_counters,
)
from core.advanced.cylinder_cv import CylinderControlVolume, slider_crank_volume
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

    def __post_init__(self) -> None:
        if self.cp is None:
            self.cp = self.gamma * self.gas_constant / max(self.gamma - 1.0, 1e-9)


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
        U = np.zeros((pipe_cells + 1, 4))
        U[1:, 0] = rho0
        U[1:, 1] = rho0 * u0
        U[1:, 2] = rho0 * (E0 + 0.5 * u0 * u0)
        U[1:, 3] = rho0
        U[0] = U[1]

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

        omega = rpm * 2.0 * math.pi / 60.0
        dt_theta = math.radians(1.0) / max(omega, 1e-9)
        cycle = 0
        last_trapped = None
        last_work = None

        while cycle < self.cfg.max_cycles:
            indicated_work = 0.0
            prev_p = None
            prev_V = None
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
                Y_cyl = cyl.m_fresh / max(cyl.m_total, 1e-9)
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
                    p0_down=p_pipe,
                    T0_down=T_pipe,
                    Y0_down=Y_pipe,
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
                Qdot = 0.0
                cyl.update(dt_theta, mdot_in, Hdot_in, Ydot_in, mdot_out, Hdot_out, Ydot_out, Qdot, dVdt)

                if mdot >= 0.0:
                    ghost_p = cyl.p
                    ghost_T = cyl.T
                    ghost_Y = Y_cyl
                else:
                    ghost_p = p_pipe
                    ghost_T = T_pipe
                    ghost_Y = Y_pipe
                ghost = ghost_state_from_nozzle(
                    ghost_p,
                    ghost_T,
                    ghost_Y,
                    mdot,
                    max(area_face, 1e-9),
                    self.cfg.gamma,
                    self.cfg.gas_constant,
                )
                t_elapsed = 0.0
                while t_elapsed < dt_theta:
                    U[0] = ghost
                    dt_cfl = cfl_dt(U, dx, self.cfg.gamma, self.cfg.gas_constant, self.cfg.cfl, self.cfg.dt_max)
                    dt_step = min(dt_cfl, dt_theta - t_elapsed)
                    U = muscl_hancock_step(
                        U,
                        dx,
                        dt_step,
                        self.cfg.gamma,
                        self.cfg.gas_constant,
                        p_outlet=p0,
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

            if last_trapped is not None and last_work is not None:
                if abs(trapped_history[-1] - last_trapped) / max(last_trapped, 1e-9) < self.cfg.convergence_tol and abs(work_history[-1] - last_work) / max(abs(last_work), 1e-9) < self.cfg.convergence_tol:
                    break
            last_trapped = trapped_history[-1]
            last_work = work_history[-1]
            cycle += 1

        return {
            "angle_deg": angle_history,
            "pressure": p_history,
            "ve": ve_history,
            "trapped_mass": trapped_history,
            "indicated_work": work_history,
        }
