from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.advanced.coupling import ghost_state_from_nozzle
from core.advanced.nozzle import nozzle_mass_flow
from core.advanced.plenum_cv import IntakePlenumConfig, ExhaustPlenumConfig, PlenumControlVolume
from core.advanced.solver_1d import cfl_dt, step_soa_python, step_soa_numba, conserved_to_primitive
from core.advanced.state import Primitive1D, primitive_to_conserved, stagnation_from_static
from core.engine_components import Engine
from core.intake_coupling import _scavenging_metrics
from core.thermo import CylinderSimulator


@dataclass
class NetworkNode:
    node_id: str
    kind: str


@dataclass
class NetworkEdge:
    src: str
    dst: str
    kind: str


@dataclass
class FullNetwork:
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]


@dataclass
class FullScopeResult:
    time_s: list[float]
    intake_plenum_pa: list[float]
    exhaust_plenum_pa: list[float]
    runner_stats: list[dict]
    per_cyl: list[dict]
    dt_min: float
    dt_max: float
    steps_used: int
    status: str


def build_full_network(engine: Engine) -> FullNetwork:
    nodes: list[NetworkNode] = []
    edges: list[NetworkEdge] = []

    nodes.append(NetworkNode("ambient", "ambient"))
    nodes.append(NetworkNode("intake_plenum", "plenum"))
    nodes.append(NetworkNode("exhaust_plenum", "plenum"))
    nodes.append(NetworkNode("exhaust_outlet", "outlet"))

    n_cyl = max(engine.block.num_cylinders, 1)
    for idx in range(n_cyl):
        cyl_id = f"cyl_{idx+1}"
        nodes.append(NetworkNode(cyl_id, "cylinder"))
        nodes.append(NetworkNode(f"intake_runner_{idx+1}", "runner_intake"))
        nodes.append(NetworkNode(f"exhaust_runner_{idx+1}", "runner_exhaust"))

        edges.append(NetworkEdge("intake_plenum", f"intake_runner_{idx+1}", "pipe"))
        edges.append(NetworkEdge(f"intake_runner_{idx+1}", cyl_id, "valve_intake"))
        edges.append(NetworkEdge(cyl_id, f"exhaust_runner_{idx+1}", "valve_exhaust"))
        edges.append(NetworkEdge(f"exhaust_runner_{idx+1}", "exhaust_plenum", "pipe"))

    edges.append(NetworkEdge("ambient", "intake_plenum", "throttle"))
    edges.append(NetworkEdge("exhaust_plenum", "exhaust_outlet", "outlet"))

    return FullNetwork(nodes=nodes, edges=edges)


def _runner_grid(length_m: float, target_dx: Optional[float]) -> tuple[int, float]:
    if length_m <= 0.0:
        raise ValueError("runner length must be positive")
    if target_dx is None or target_dx <= 0.0:
        n_cells = 20
    else:
        n_cells = int(max(3, round(length_m / target_dx)))
    dx = length_m / max(n_cells, 1)
    return n_cells, dx


def _init_runner_state(
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


def _valve_area(engine: Engine, angle_deg: float, intake: bool) -> float:
    lift_mm = engine.camshaft.get_lift(angle_deg, intake=intake)
    lift_m = max(lift_mm * 1e-3, 0.0)
    seat_mm = engine.head.intake_valve_diameter_mm if intake else engine.head.exhaust_valve_diameter_mm
    seat_diam_m = max(seat_mm * 1e-3, 1e-6)
    n_valves = engine.head.intake_valves if intake else engine.head.exhaust_valves
    area = math.pi * seat_diam_m * lift_m * max(n_valves, 1)
    cd = float(np.clip(engine.head.port_flow_efficiency, 0.05, 1.0))
    return cd * max(area, 0.0)


def _interp_cycle(angle_deg: float, angle_arr: np.ndarray, values: np.ndarray) -> float:
    return float(np.interp(angle_deg, angle_arr, values))


def run_full_scope(
    engine: Engine,
    *,
    duration_s: float,
    max_steps: Optional[int] = None,
    target_dx: Optional[float] = None,
    use_numba: bool = False,
    time_budget_ms: Optional[float] = None,
    rpm: Optional[float] = None,
) -> FullScopeResult:
    if duration_s <= 0.0:
        raise ValueError("duration must be positive")
    max_steps = int(max_steps) if max_steps is not None else int(duration_s * 4000) + 50
    if max_steps < 1:
        raise ValueError("max_steps must be >= 1")

    rpm = max(engine.camshaft.peak_rpm, 500.0) if rpm is None else float(rpm)

    gamma = float(engine.simulation_settings.gamma_air)
    gas_constant = float(engine.simulation_settings.gas_constant_R)
    cp = gamma * gas_constant / max(gamma - 1.0, 1e-9)
    cp_model = str(engine.simulation_settings.cp_model)

    p_amb = float(engine.simulation_settings.air_pressure_bar) * 1e5
    T_amb = float(engine.simulation_settings.air_temperature_c) + 273.15
    Y_air = 1.0

    n_cyl = max(engine.block.num_cylinders, 1)
    firing_order = list(engine.block.firing_order)
    if not firing_order:
        firing_order = list(range(1, n_cyl + 1))
    phase_map = {cyl_id: idx * (720.0 / n_cyl) for idx, cyl_id in enumerate(firing_order)}

    sim = CylinderSimulator(engine)
    cycle = sim.run_cycle(rpm, _disable_intake_coupling=True)
    angle_arr = np.asarray(cycle["angle"], dtype=float)
    cyl_pressure = np.asarray(cycle["pressure"], dtype=float)
    cyl_temp = np.asarray(cycle["temperature"], dtype=float)

    length_intake_m = float(engine.intake.runner_length) * 1e-3
    dia_intake_m = float(engine.intake.runner_diameter) * 1e-3
    area_intake = math.pi * (dia_intake_m * 0.5) ** 2

    length_exhaust_m = float(engine.exhaust.header_primary_length) * 1e-3
    dia_exhaust_m = float(engine.exhaust.header_primary_diameter) * 1e-3
    area_exhaust = math.pi * (dia_exhaust_m * 0.5) ** 2

    n_cells_intake, dx_intake = _runner_grid(length_intake_m, target_dx)
    n_cells_exhaust, dx_exhaust = _runner_grid(length_exhaust_m, target_dx)

    intake_runners = [
        _init_runner_state(n_cells_intake, p_amb, T_amb, Y_air, gamma, gas_constant) for _ in range(n_cyl)
    ]
    exhaust_runners = [
        _init_runner_state(n_cells_exhaust, p_amb, T_amb, 0.0, gamma, gas_constant) for _ in range(n_cyl)
    ]

    intake_plenum_cfg = IntakePlenumConfig.from_dict(engine.simulation_settings.intake_plenum or {})
    intake_plenum_cfg.enabled = True
    intake_plenum_cfg.volume_m3 = max(float(engine.intake.plenum_volume) * 1e-3, 1e-6)
    intake_plenum_cfg.p_init_pa = p_amb
    intake_plenum_cfg.t_init_k = T_amb
    intake_plenum_cfg.y_init = Y_air
    intake_plenum = PlenumControlVolume(
        intake_plenum_cfg,
        gas_constant,
        cp,
        gamma,
        p_amb=p_amb,
        T_amb=T_amb,
        Y_amb=Y_air,
    )

    exhaust_volume = area_exhaust * max(float(engine.exhaust.collector_length) * 1e-3, 0.05)
    exhaust_plenum_cfg = ExhaustPlenumConfig.from_dict(engine.simulation_settings.exhaust_plenum or {})
    exhaust_plenum_cfg.enabled = True
    exhaust_plenum_cfg.volume_m3 = max(exhaust_volume, 1e-6)
    exhaust_plenum_cfg.p_init_pa = p_amb
    exhaust_plenum_cfg.t_init_k = max(T_amb + 50.0, 300.0)
    exhaust_plenum_cfg.y_init = 0.0
    exhaust_plenum = PlenumControlVolume(
        exhaust_plenum_cfg,
        gas_constant,
        cp,
        gamma,
        p_amb=p_amb,
        T_amb=T_amb,
        Y_amb=0.0,
    )

    time_s: list[float] = []
    intake_plenum_pa: list[float] = []
    exhaust_plenum_pa: list[float] = []

    stats = [
        {
            "cyl_id": idx + 1,
            "intake_min": float("inf"),
            "intake_max": -float("inf"),
            "intake_sum_sq": 0.0,
            "intake_count": 0,
            "exhaust_min": float("inf"),
            "exhaust_max": -float("inf"),
            "exhaust_sum_sq": 0.0,
            "exhaust_count": 0,
        }
        for idx in range(n_cyl)
    ]

    t_now = 0.0
    dt_min = float("inf")
    dt_max = 0.0
    decimate = 5

    stepper = step_soa_numba if use_numba else step_soa_python
    start_time = time.perf_counter()
    for step in range(max_steps):
        if time_budget_ms is not None:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            if elapsed_ms > float(time_budget_ms):
                raise RuntimeError("full-scope exceeded time_budget_ms")
        if t_now >= duration_s:
            status = "complete"
            break

        mdot_plenum_total = 0.0
        Hdot_plenum_total = 0.0
        Ydot_plenum_total = 0.0
        intake_ghost_right = []

        mdot_exhaust_total = 0.0
        Hdot_exhaust_total = 0.0
        Ydot_exhaust_total = 0.0
        exhaust_ghost_right = []

        # Prepare ghosts and total flows for each cylinder
        for idx in range(n_cyl):
            cyl_id = idx + 1
            phase_deg = phase_map.get(cyl_id, 0.0)
            angle_deg = (t_now * rpm * 6.0 + phase_deg) % 720.0
            p_cyl = max(_interp_cycle(angle_deg, angle_arr, cyl_pressure), 1e3)
            T_cyl = max(_interp_cycle(angle_deg, angle_arr, cyl_temp), 200.0)

            # Intake runner
            U_int = intake_runners[idx]
            prim_in = conserved_to_primitive(U_int[1:2], gamma, gas_constant)[0]
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
            area_valve = _valve_area(engine, angle_deg, intake=True)
            mdot_valve, _, _ = nozzle_mass_flow(
                p_cyl,
                T_cyl,
                p_pipe,
                area_valve,
                gamma,
                gas_constant,
                cp,
                Y_air,
                p0_down=p0_pipe,
                T0_down=T0_pipe,
                Y0_down=Y_pipe,
                cp_model=cp_model,
            )
            if mdot_valve >= 0.0:
                ghost_p0 = p_cyl
                ghost_T0 = T_cyl
                ghost_Y0 = Y_air
            else:
                ghost_p0 = p0_pipe
                ghost_T0 = T0_pipe
                ghost_Y0 = Y_pipe
            ghost_left = ghost_state_from_nozzle(
                ghost_p0,
                ghost_T0,
                ghost_Y0,
                mdot_valve,
                max(area_intake, 1e-9),
                gamma,
                gas_constant,
                phase="phase2",
                cp_model=cp_model,
            )
            U_int[0] = ghost_left

            prim_out = conserved_to_primitive(U_int[-2:-1], gamma, gas_constant)[0]
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
            mdot_plenum, Hdot_plenum, Ydot_plenum = nozzle_mass_flow(
                intake_plenum.p,
                intake_plenum.T,
                p_pipe_out,
                area_intake,
                gamma,
                gas_constant,
                cp,
                intake_plenum.Y,
                p0_down=p0_pipe_out,
                T0_down=T0_pipe_out,
                Y0_down=Y_pipe_out,
                cp_model=cp_model,
            )
            mdot_plenum_total += mdot_plenum
            Hdot_plenum_total += Hdot_plenum
            Ydot_plenum_total += Ydot_plenum
            if mdot_plenum >= 0.0:
                ghost_p0 = intake_plenum.p
                ghost_T0 = intake_plenum.T
                ghost_Y0 = intake_plenum.Y
            else:
                ghost_p0 = p0_pipe_out
                ghost_T0 = T0_pipe_out
                ghost_Y0 = Y_pipe_out
            intake_ghost_right.append(
                ghost_state_from_nozzle(
                    ghost_p0,
                    ghost_T0,
                    ghost_Y0,
                    mdot_plenum,
                    max(area_intake, 1e-9),
                    gamma,
                    gas_constant,
                    phase="phase2",
                    cp_model=cp_model,
                )
            )

            # Exhaust runner
            U_exh = exhaust_runners[idx]
            prim_in = conserved_to_primitive(U_exh[1:2], gamma, gas_constant)[0]
            p_pipe_exh = float(prim_in[2])
            T_pipe_exh = float(prim_in[3])
            Y_pipe_exh = float(prim_in[4])
            u_pipe_exh = float(prim_in[1])
            p0_pipe_exh, T0_pipe_exh = stagnation_from_static(
                p_pipe_exh,
                T_pipe_exh,
                u_pipe_exh,
                gamma,
                gas_constant,
                cp_model=cp_model,
                Y_fresh=Y_pipe_exh,
            )
            area_valve_exh = _valve_area(engine, angle_deg, intake=False)
            mdot_exh, _, _ = nozzle_mass_flow(
                p_cyl,
                T_cyl,
                p_pipe_exh,
                area_valve_exh,
                gamma,
                gas_constant,
                cp,
                0.0,
                p0_down=p0_pipe_exh,
                T0_down=T0_pipe_exh,
                Y0_down=Y_pipe_exh,
                cp_model=cp_model,
            )
            if mdot_exh >= 0.0:
                ghost_p0 = p_cyl
                ghost_T0 = T_cyl
                ghost_Y0 = 0.0
            else:
                ghost_p0 = p0_pipe_exh
                ghost_T0 = T0_pipe_exh
                ghost_Y0 = Y_pipe_exh
            U_exh[0] = ghost_state_from_nozzle(
                ghost_p0,
                ghost_T0,
                ghost_Y0,
                mdot_exh,
                max(area_exhaust, 1e-9),
                gamma,
                gas_constant,
                phase="phase2",
                cp_model=cp_model,
            )

            prim_out = conserved_to_primitive(U_exh[-2:-1], gamma, gas_constant)[0]
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
            mdot_plenum_ex, Hdot_plenum_ex, Ydot_plenum_ex = nozzle_mass_flow(
                p0_pipe_out,
                T0_pipe_out,
                exhaust_plenum.p,
                area_exhaust,
                gamma,
                gas_constant,
                cp,
                Y_pipe_out,
                p0_down=exhaust_plenum.p,
                T0_down=exhaust_plenum.T,
                Y0_down=exhaust_plenum.Y,
                cp_model=cp_model,
            )
            mdot_exhaust_total += -mdot_plenum_ex
            Hdot_exhaust_total += -Hdot_plenum_ex
            Ydot_exhaust_total += -Ydot_plenum_ex
            if mdot_plenum_ex >= 0.0:
                ghost_p0 = p0_pipe_out
                ghost_T0 = T0_pipe_out
                ghost_Y0 = Y_pipe_out
            else:
                ghost_p0 = exhaust_plenum.p
                ghost_T0 = exhaust_plenum.T
                ghost_Y0 = exhaust_plenum.Y
            exhaust_ghost_right.append(
                ghost_state_from_nozzle(
                    ghost_p0,
                    ghost_T0,
                    ghost_Y0,
                    mdot_plenum_ex,
                    max(area_exhaust, 1e-9),
                    gamma,
                    gas_constant,
                    phase="phase2",
                    cp_model=cp_model,
                )
            )

        # Intake throttle -> plenum
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
            area_eff_throttle = area_intake

        mdot_throttle, Hdot_throttle, Ydot_throttle = nozzle_mass_flow(
            p_amb,
            T_amb,
            intake_plenum.p,
            area_eff_throttle,
            gamma,
            gas_constant,
            cp,
            Y_air,
            p0_down=intake_plenum.p,
            T0_down=intake_plenum.T,
            Y0_down=intake_plenum.Y,
            cp_model=cp_model,
        )

        outlet_area = max(area_exhaust * n_cyl, 1e-6)
        mdot_out, Hdot_out, Ydot_out = nozzle_mass_flow(
            exhaust_plenum.p,
            exhaust_plenum.T,
            p_amb,
            outlet_area,
            gamma,
            gas_constant,
            cp,
            exhaust_plenum.Y,
            p0_down=p_amb,
            T0_down=T_amb,
            Y0_down=0.0,
            cp_model=cp_model,
        )

        # Compute dt from min CFL across runners
        dt_candidates = []
        for idx in range(n_cyl):
            U_int = intake_runners[idx]
            U_int[-1] = intake_ghost_right[idx]
            dt_candidates.append(cfl_dt(U_int, dx_intake, gamma, gas_constant, 0.5, 1e-3, 1, 1))
            U_exh = exhaust_runners[idx]
            U_exh[-1] = exhaust_ghost_right[idx]
            dt_candidates.append(cfl_dt(U_exh, dx_exhaust, gamma, gas_constant, 0.5, 1e-3, 1, 1))
        dt = min(dt_candidates) if dt_candidates else 1e-4
        dt = max(min(dt, duration_s - t_now), 1e-6)

        intake_plenum.update(
            dt,
            mdot_throttle,
            Hdot_throttle,
            Ydot_throttle,
            mdot_plenum_total,
            Hdot_plenum_total,
            Ydot_plenum_total,
        )

        exhaust_plenum.update(
            dt,
            -mdot_out,
            -Hdot_out,
            -Ydot_out,
            mdot_exhaust_total,
            Hdot_exhaust_total,
            Ydot_exhaust_total,
        )

        for idx in range(n_cyl):
            intake_runners[idx] = stepper(
                intake_runners[idx],
                dx_intake,
                dt,
                gamma,
                gas_constant,
                friction_factor=0.0,
                diameter=dia_intake_m,
                outlet_mode="copy",
            )
            exhaust_runners[idx] = stepper(
                exhaust_runners[idx],
                dx_exhaust,
                dt,
                gamma,
                gas_constant,
                friction_factor=0.0,
                diameter=dia_exhaust_m,
                outlet_mode="copy",
            )

            p_int = conserved_to_primitive(intake_runners[idx][1:-1], gamma, gas_constant)[:, 2]
            p_exh = conserved_to_primitive(exhaust_runners[idx][1:-1], gamma, gas_constant)[:, 2]
            stats[idx]["intake_min"] = float(min(stats[idx]["intake_min"], float(np.min(p_int))))
            stats[idx]["intake_max"] = float(max(stats[idx]["intake_max"], float(np.max(p_int))))
            stats[idx]["intake_sum_sq"] += float(np.sum(p_int ** 2))
            stats[idx]["intake_count"] += p_int.size
            stats[idx]["exhaust_min"] = float(min(stats[idx]["exhaust_min"], float(np.min(p_exh))))
            stats[idx]["exhaust_max"] = float(max(stats[idx]["exhaust_max"], float(np.max(p_exh))))
            stats[idx]["exhaust_sum_sq"] += float(np.sum(p_exh ** 2))
            stats[idx]["exhaust_count"] += p_exh.size

        t_now += dt
        dt_min = min(dt_min, dt)
        dt_max = max(dt_max, dt)

        if step % decimate == 0:
            time_s.append(float(t_now))
            intake_plenum_pa.append(float(intake_plenum.p))
            exhaust_plenum_pa.append(float(exhaust_plenum.p))
    else:
        status = "max_steps"
        raise RuntimeError("full-scope exceeded max_steps")

    runner_stats = []
    for entry in stats:
        intake_rms = math.sqrt(entry["intake_sum_sq"] / max(entry["intake_count"], 1))
        exhaust_rms = math.sqrt(entry["exhaust_sum_sq"] / max(entry["exhaust_count"], 1))
        runner_stats.append(
            {
                "cyl_id": entry["cyl_id"],
                "intake_min": entry["intake_min"],
                "intake_max": entry["intake_max"],
                "intake_rms": intake_rms,
                "exhaust_min": entry["exhaust_min"],
                "exhaust_max": entry["exhaust_max"],
                "exhaust_rms": exhaust_rms,
            }
        )

    plenum_mean = float(np.mean(intake_plenum_pa)) if intake_plenum_pa else float(intake_plenum.p)
    per_cyl = []
    for idx in range(n_cyl):
        metrics = _scavenging_metrics(engine, rpm, plenum_mean, float(cycle.get("airflow_cfm", 0.0)))
        per_cyl.append(
            {
                "cyl_id": idx + 1,
                "rpm": float(rpm),
                "ve_actual": float(cycle.get("ve_actual", 0.0)),
                "mean_torque_nm": float(cycle.get("mean_torque_nm", 0.0)),
                "map_est_kpa": float(plenum_mean / 1000.0),
                "residual_fraction_est": float(metrics["residual_fraction_est"]),
                "scavenging_index": float(metrics["scavenging_index"]),
            }
        )

    return FullScopeResult(
        time_s=time_s,
        intake_plenum_pa=intake_plenum_pa,
        exhaust_plenum_pa=exhaust_plenum_pa,
        runner_stats=runner_stats,
        per_cyl=per_cyl,
        dt_min=float(dt_min if math.isfinite(dt_min) else 0.0),
        dt_max=float(dt_max),
        steps_used=int(step + 1),
        status=status,
    )
