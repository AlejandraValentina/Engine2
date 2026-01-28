from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.advanced.coupling import ghost_state_from_nozzle
from core.advanced.nozzle import nozzle_mass_flow
from core.advanced.plenum_cv import IntakePlenumConfig, PlenumControlVolume
from core.advanced.solver_1d import cfl_dt, step_soa_python, conserved_to_primitive
from core.advanced.state import Primitive1D, primitive_to_conserved, stagnation_from_static
from core.engine_components import Engine


@dataclass
class IntakeScopeResult:
    time_s: list[float]
    plenum_pressure_pa: list[float]
    runner_pressure_pa: list[list[float]]
    valve_area_m2: list[float]


def _intake_valve_area(engine: Engine, angle_deg: float) -> float:
    lift_mm = engine.camshaft.get_lift(angle_deg, intake=True)
    lift_m = max(lift_mm * 1e-3, 0.0)
    seat_diam_m = max(engine.head.intake_valve_diameter_mm * 1e-3, 1e-6)
    n_valves = max(engine.head.intake_valves, 1)
    area = math.pi * seat_diam_m * lift_m * n_valves
    cd = float(np.clip(engine.head.port_flow_efficiency, 0.05, 1.0))
    return cd * max(area, 0.0)


def _initial_runner_state(
    n_cells: int,
    p0: float,
    T0: float,
    Y0: float,
    gamma: float,
    gas_constant: float,
) -> np.ndarray:
    rho = max(p0 / max(gas_constant * T0, 1e-9), 1e-9)
    prim = Primitive1D(rho=rho, u=0.0, p=p0, T=T0, Y=Y0)
    cons = primitive_to_conserved(prim, gamma, gas_constant)
    U = np.zeros((n_cells + 2, 4), dtype=float)
    U[1:-1, 0] = cons.rho
    U[1:-1, 1] = cons.rhou
    U[1:-1, 2] = cons.rhoE
    U[1:-1, 3] = cons.rhoY
    U[0] = U[1]
    U[-1] = U[-2]
    return U


def _runner_discretization(length_m: float, target_dx: Optional[float]) -> tuple[int, float]:
    if length_m <= 0.0:
        raise ValueError("runner length must be positive")
    if target_dx is None or target_dx <= 0.0:
        n_cells = 20
    else:
        n_cells = int(max(3, round(length_m / target_dx)))
    dx = length_m / max(n_cells, 1)
    return n_cells, dx


def run_intake_scope(
    engine: Engine,
    *,
    max_steps: Optional[int] = None,
    target_dx: Optional[float] = None,
    rpm: Optional[float] = None,
    cylinder_pressure_trace: Optional[dict] = None,
) -> IntakeScopeResult:
    max_steps = 400 if max_steps is None or max_steps <= 0 else int(max_steps)
    rpm = max(engine.camshaft.peak_rpm, 500.0) if rpm is None else float(rpm)

    gamma = float(engine.simulation_settings.gamma_air)
    gas_constant = float(engine.simulation_settings.gas_constant_R)
    cp = gamma * gas_constant / max(gamma - 1.0, 1e-9)
    cp_model = str(engine.simulation_settings.cp_model)

    p_amb = float(engine.simulation_settings.air_pressure_bar) * 1e5
    T_amb = float(engine.simulation_settings.air_temperature_c) + 273.15
    Y_amb = 1.0

    length_m = float(engine.intake.runner_length) * 1e-3
    diameter_m = float(engine.intake.runner_diameter) * 1e-3
    area_face = math.pi * (diameter_m * 0.5) ** 2
    n_cells, dx = _runner_discretization(length_m, target_dx)

    U = _initial_runner_state(n_cells, p_amb, T_amb, Y_amb, gamma, gas_constant)

    plenum_cfg = IntakePlenumConfig(
        enabled=True,
        volume_m3=max(float(engine.intake.plenum_volume) * 1e-3, 1e-6),
        p_init_pa=p_amb,
        t_init_k=T_amb,
        y_init=Y_amb,
    )
    plenum = PlenumControlVolume(
        plenum_cfg,
        gas_constant,
        cp,
        gamma,
        p_amb=p_amb,
        T_amb=T_amb,
        Y_amb=Y_amb,
    )

    time_s: list[float] = []
    plenum_pressure_pa: list[float] = []
    runner_pressure_pa: list[list[float]] = []
    valve_area_m2: list[float] = []

    time = 0.0
    cfl = 0.5
    dt_max = 1e-3

    angle_trace = None
    pressure_trace = None
    if cylinder_pressure_trace is not None:
        angle_trace = np.asarray(cylinder_pressure_trace.get("angle", []), dtype=float)
        pressure_trace = np.asarray(cylinder_pressure_trace.get("pressure", []), dtype=float)
        finite = np.isfinite(angle_trace) & np.isfinite(pressure_trace)
        if np.any(finite):
            angle_trace = angle_trace[finite]
            pressure_trace = pressure_trace[finite]
        if angle_trace.size < 2:
            angle_trace = None
            pressure_trace = None

    for _ in range(max_steps):
        prim_in = conserved_to_primitive(U[1:2], gamma, gas_constant)[0]
        p_pipe = float(prim_in[2])
        T_pipe = float(prim_in[3])
        Y_pipe = float(prim_in[4])
        u_pipe = float(prim_in[1])
        p0_pipe, T0_pipe = stagnation_from_static(
            p_pipe,
            T_pipe,
            u_pipe,
            gamma,
            gas_constant,
            cp_model=cp_model,
            Y_fresh=Y_pipe,
        )

        angle_deg = (time * rpm * 6.0) % 720.0
        area_valve = _intake_valve_area(engine, angle_deg)

        if angle_trace is not None and pressure_trace is not None:
            p_cyl = float(np.interp(angle_deg, angle_trace, pressure_trace))
            p_cyl = max(p_cyl, 1e3)
        else:
            p_cyl = 0.95 * p_amb
        T_cyl = T_amb
        Y_cyl = 1.0

        mdot_valve, Hdot_valve, Ydot_valve = nozzle_mass_flow(
            p_cyl,
            T_cyl,
            p_pipe,
            area_valve,
            gamma,
            gas_constant,
            cp,
            Y_cyl,
            p0_down=p0_pipe,
            T0_down=T0_pipe,
            Y0_down=Y_pipe,
            cp_model=cp_model,
        )
        if mdot_valve >= 0.0:
            ghost_p0 = p_cyl
            ghost_T0 = T_cyl
            ghost_Y0 = Y_cyl
        else:
            ghost_p0 = p0_pipe
            ghost_T0 = T0_pipe
            ghost_Y0 = Y_pipe
        ghost_left = ghost_state_from_nozzle(
            ghost_p0,
            ghost_T0,
            ghost_Y0,
            mdot_valve,
            max(area_face, 1e-9),
            gamma,
            gas_constant,
            phase="phase2",
            cp_model=cp_model,
        )

        prim_out = conserved_to_primitive(U[-2:-1], gamma, gas_constant)[0]
        p_pipe_out = float(prim_out[2])
        T_pipe_out = float(prim_out[3])
        Y_pipe_out = float(prim_out[4])
        u_pipe_out = float(prim_out[1])
        p0_pipe_out, T0_pipe_out = stagnation_from_static(
            p_pipe_out,
            T_pipe_out,
            u_pipe_out,
            gamma,
            gas_constant,
            cp_model=cp_model,
            Y_fresh=Y_pipe_out,
        )

        if engine.throttle.enabled:
            if engine.throttle.body_diam_m <= 0.0:
                raise ValueError("throttle.body_diam_m must be positive when enabled")
            body_diam = engine.throttle.body_diam_m
            pos = min(max(engine.throttle.position, 0.0), 1.0)
            exponent = engine.throttle.area_exponent
            if engine.throttle.safety_clamps:
                exponent = max(exponent, 1.0)
            area_max = math.pi * (body_diam * 0.5) ** 2
            area_eff_throttle = engine.throttle.cd * area_max * (pos ** exponent)
        else:
            area_eff_throttle = area_face

        mdot_throttle, Hdot_throttle, Ydot_throttle = nozzle_mass_flow(
            p_amb,
            T_amb,
            plenum.p,
            area_eff_throttle,
            gamma,
            gas_constant,
            cp,
            Y_amb,
            p0_down=plenum.p,
            T0_down=plenum.T,
            Y0_down=plenum.Y,
            cp_model=cp_model,
        )

        mdot_plenum, Hdot_plenum, Ydot_plenum = nozzle_mass_flow(
            plenum.p,
            plenum.T,
            p_pipe_out,
            area_face,
            gamma,
            gas_constant,
            cp,
            plenum.Y,
            p0_down=p0_pipe_out,
            T0_down=T0_pipe_out,
            Y0_down=Y_pipe_out,
            cp_model=cp_model,
        )

        if mdot_plenum >= 0.0:
            ghost_p0 = plenum.p
            ghost_T0 = plenum.T
            ghost_Y0 = plenum.Y
        else:
            ghost_p0 = p0_pipe_out
            ghost_T0 = T0_pipe_out
            ghost_Y0 = Y_pipe_out
        ghost_right = ghost_state_from_nozzle(
            ghost_p0,
            ghost_T0,
            ghost_Y0,
            mdot_plenum,
            max(area_face, 1e-9),
            gamma,
            gas_constant,
            phase="phase2",
            cp_model=cp_model,
        )

        dt = cfl_dt(
            U,
            dx,
            gamma,
            gas_constant,
            cfl,
            dt_max,
            ghost_left=1,
            ghost_right=1,
        )

        plenum.update(
            dt,
            mdot_throttle,
            Hdot_throttle,
            Ydot_throttle,
            mdot_plenum,
            Hdot_plenum,
            Ydot_plenum,
        )

        U[0] = ghost_left
        U[-1] = ghost_right
        U = step_soa_python(
            U,
            dx,
            dt,
            gamma,
            gas_constant,
            friction_factor=0.0,
            diameter=diameter_m,
            outlet_mode="copy",
        )

        time += dt
        time_s.append(float(time))
        plenum_pressure_pa.append(float(plenum.p))
        runner_pressure_pa.append(
            [float(val) for val in conserved_to_primitive(U[1:-1], gamma, gas_constant)[:, 2]]
        )
        valve_area_m2.append(float(area_valve))

    return IntakeScopeResult(
        time_s=time_s,
        plenum_pressure_pa=plenum_pressure_pa,
        runner_pressure_pa=runner_pressure_pa,
        valve_area_m2=valve_area_m2,
    )
