from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from core.advanced.coupling import ValveTiming, boundary_flux_from_nozzle, ghost_state_from_nozzle
from core.advanced.cylinder_cv import CylinderControlVolume, slider_crank_volume
from core.advanced.solver_1d import cfl_dt, muscl_hancock_step


@dataclass
class OrchestratorConfig:
    gamma: float = 1.35
    gas_constant: float = 287.0
    cp: float = 1005.0
    cfl: float = 0.5
    dt_max: float = 5e-5
    max_cycles: int = 5
    convergence_tol: float = 0.005


class Orchestrator:
    def __init__(self, config: OrchestratorConfig) -> None:
        self.cfg = config

    def run(
        self,
        rpm: float,
        pipe_cells: int,
        pipe_length_m: float,
        bore_m: float,
        stroke_m: float,
        conrod_m: float,
        clearance_m3: float,
        valve: ValveTiming,
    ) -> Dict[str, List[float]]:
        dx = pipe_length_m / pipe_cells
        rho0 = 1.2
        u0 = 0.0
        p0 = 101325.0
        T0 = p0 / (rho0 * self.cfg.gas_constant)
        E0 = self.cfg.gas_constant * T0 / (self.cfg.gamma - 1.0)
        U = np.zeros((pipe_cells, 4))
        U[:, 0] = rho0
        U[:, 1] = rho0 * u0
        U[:, 2] = rho0 * (E0 + 0.5 * u0 * u0)
        U[:, 3] = rho0

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
        dt = self.cfg.dt_max
        cycle = 0
        last_trapped = None
        last_work = None

        while cycle < self.cfg.max_cycles:
            indicated_work = 0.0
            for step in range(int(720.0 / 1.0)):
                angle_deg = step
                theta = math.radians(angle_deg)
                V, dVdtheta = slider_crank_volume(theta, bore_m, stroke_m, conrod_m, clearance_m3)
                cyl.V = V
                dVdt = dVdtheta * omega

                area = valve.area_eff(angle_deg)
                mdot, Hdot, Ydot, _ = boundary_flux_from_nozzle(
                    cyl.p,
                    cyl.T,
                    cyl.m_fresh / max(cyl.m_total, 1e-9),
                    p0,
                    area,
                    self.cfg.gamma,
                    self.cfg.gas_constant,
                    valve.cd,
                    self.cfg.cp,
                )

                Qdot = 0.0
                cyl.update(dt, mdot, Hdot, Ydot, 0.0, 0.0, 0.0, Qdot, dVdt)

                ghost = ghost_state_from_nozzle(
                    cyl.p,
                    cyl.T,
                    cyl.m_fresh / max(cyl.m_total, 1e-9),
                    mdot,
                    max(area, 1e-9),
                    self.cfg.gamma,
                    self.cfg.gas_constant,
                )
                U[0] = ghost
                U = muscl_hancock_step(U, dx, dt, self.cfg.gamma, self.cfg.gas_constant)

                dt = cfl_dt(U, dx, self.cfg.gamma, self.cfg.gas_constant, self.cfg.cfl, self.cfg.dt_max)

                angle_history.append(angle_deg + cycle * 720.0)
                p_history.append(cyl.p)
                ve_history.append(cyl.m_fresh / max(rho0 * (math.pi * (bore_m * 0.5) ** 2) * stroke_m, 1e-9))
                indicated_work += cyl.p * dVdtheta * math.radians(1.0)

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
