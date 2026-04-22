from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.engine_components import Engine
from core.intake_scope import run_intake_scope
from core.thermo import CylinderSimulator


@dataclass
class IntakeCouplingConfig:
    enabled: bool = False
    max_iters: int = 4
    map_tol_pa: float = 50.0
    under_relax: float = 0.5
    max_steps: int = 200
    target_dx: float | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "IntakeCouplingConfig":
        return cls(
            enabled=bool(data.get("enabled", False)),
            max_iters=int(data.get("max_iters", 4)),
            map_tol_pa=float(data.get("map_tol_pa", 50.0)),
            under_relax=float(data.get("under_relax", 0.5)),
            max_steps=int(data.get("max_steps", 200)),
            target_dx=data.get("target_dx"),
        )


def _estimate_map_pa(result) -> float:
    valve_area = np.asarray(result.valve_area_m2, dtype=float)
    pressure_matrix = np.asarray(result.runner_pressure_pa, dtype=float)
    if pressure_matrix.ndim != 2 or pressure_matrix.shape[0] == 0:
        raise ValueError("Invalid runner pressure matrix for MAP estimate")
    p_valve = pressure_matrix[:, 0]
    if valve_area.shape[0] != p_valve.shape[0]:
        raise ValueError("Valve area and pressure series length mismatch")
    mask = valve_area > 0.0
    if np.any(mask):
        p_use = p_valve[mask]
    else:
        p_use = p_valve
    if p_use.size == 0:
        raise ValueError("MAP estimate has no samples")
    if not np.isfinite(p_use).all():
        raise ValueError("Non-finite MAP samples")
    return float(np.mean(p_use))


def _overlap_deg(engine: Engine, step_deg: float = 0.5) -> float:
    angles = np.arange(0.0, 720.0 + step_deg, step_deg)
    intake_open = np.array([engine.camshaft.get_lift(a, intake=True) > 0.0 for a in angles])
    exhaust_open = np.array([engine.camshaft.get_lift(a, intake=False) > 0.0 for a in angles])
    overlap = intake_open & exhaust_open
    return float(np.count_nonzero(overlap) * step_deg)


def _scavenging_metrics(engine: Engine, rpm: float, map_pa: float, airflow_cfm: float) -> dict:
    overlap = _overlap_deg(engine)
    overlap_fraction = max(min(overlap / 720.0, 1.0), 0.0)
    gas_constant = float(engine.simulation_settings.gas_constant_R)
    ambient_temp_k = float(engine.simulation_settings.air_temperature_c) + 273.15
    rho = map_pa / max(gas_constant * ambient_temp_k, 1e-9)
    flow_m3_s = airflow_cfm * 0.0283168 / 60.0
    m_dot = rho * flow_m3_s
    cycle_time = 120.0 / max(rpm, 1e-3)
    m_cycle = max(m_dot * cycle_time, 1e-12)
    overlap_flow = overlap_fraction * m_cycle
    residual_fraction = overlap_flow / m_cycle
    scavenging_index = max(1.0 - residual_fraction, 0.0)
    return {
        "overlap_flow_kg": float(max(overlap_flow, 0.0)),
        "residual_fraction_est": float(max(residual_fraction, 0.0)),
        "scavenging_index": float(scavenging_index),
    }


def run_intake_coupled_cycle(simulator: CylinderSimulator, rpm: float, cfg_dict: dict) -> dict:
    cfg = IntakeCouplingConfig.from_dict(cfg_dict)
    if not cfg.enabled:
        return simulator.run_cycle(rpm, _disable_intake_coupling=True)
    if cfg.max_iters < 1:
        raise ValueError("intake_coupling.max_iters must be >= 1")
    if cfg.map_tol_pa <= 0.0:
        raise ValueError("intake_coupling.map_tol_pa must be positive")

    settings = simulator.engine.simulation_settings
    p_amb = float(settings.air_pressure_bar) * 1e5
    map_guess = p_amb

    last_map = None
    cycle = None
    for iter_index in range(cfg.max_iters):
        cycle = simulator.run_cycle(rpm, intake_map_pa=map_guess, _disable_intake_coupling=True)
        trace = {
            "angle": cycle["angle"],
            "pressure": cycle["pressure"],
        }
        scope = run_intake_scope(
            simulator.engine,
            max_steps=cfg.max_steps,
            target_dx=cfg.target_dx,
            rpm=rpm,
            cylinder_pressure_trace=trace,
        )
        map_new = _estimate_map_pa(scope)
        if iter_index == 0 and cfg.max_iters == 1:
            map_guess = map_new
            break
        if last_map is not None and abs(map_new - map_guess) <= cfg.map_tol_pa:
            map_guess = map_new
            break
        map_guess = map_guess + cfg.under_relax * (map_new - map_guess)
        last_map = map_new
    else:
        raise RuntimeError("intake coupling did not converge within max_iters")

    if cycle is None:
        raise RuntimeError("intake coupling failed to produce cycle")

    metrics = _scavenging_metrics(simulator.engine, rpm, map_guess, float(cycle.get("airflow_cfm", 0.0)))
    cycle = dict(cycle)
    cycle["map_est_kpa"] = float(map_guess / 1000.0)
    cycle.update(metrics)
    return cycle
