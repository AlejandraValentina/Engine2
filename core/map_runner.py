from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@dataclass
class MapPoint:
    rpm: float
    throttle: float
    torque_nm: float
    power_hp: float
    bmep_bar: float
    ve_actual: float
    map_est_kpa: float | None
    fuel_gps: float | None = None
    bsfc_gpkwh: float | None = None

    def to_dict(self) -> dict:
        payload = {
            "rpm": float(self.rpm),
            "throttle": float(self.throttle),
            "torque_nm": float(self.torque_nm),
            "power_hp": float(self.power_hp),
            "bmep_bar": float(self.bmep_bar),
            "ve_actual": float(self.ve_actual),
            "map_est_kpa": float(self.map_est_kpa) if self.map_est_kpa is not None else None,
        }
        if self.fuel_gps is not None:
            payload["fuel_gps"] = float(self.fuel_gps)
        if self.bsfc_gpkwh is not None:
            payload["bsfc_gpkwh"] = float(self.bsfc_gpkwh)
        return payload


def _air_density(settings, map_est_kpa: float | None) -> float:
    gas_constant = float(settings.gas_constant_R)
    temp_k = float(settings.air_temperature_c) + 273.15
    if map_est_kpa is None:
        p_pa = float(settings.air_pressure_bar) * 1e5
    else:
        p_pa = max(float(map_est_kpa) * 1000.0, 1.0)
    return p_pa / max(gas_constant * temp_k, 1e-9)


def _fuel_metrics(engine: Engine, cycle: dict, map_est_kpa: float | None) -> tuple[float | None, float | None]:
    fuel_cfg = getattr(engine.simulation_settings, "fuel", None)
    if fuel_cfg is None or not getattr(fuel_cfg, "enabled", False):
        return None, None

    airflow_cfm = float(cycle.get("airflow_cfm", 0.0))
    flow_m3_s = airflow_cfm * 0.0283168 / 60.0
    rho = _air_density(engine.simulation_settings, map_est_kpa)
    m_dot_air = rho * flow_m3_s

    afr = float(getattr(engine.combustion, "afr", getattr(engine.fuel, "stoich_afr", 14.7)))
    afr = max(afr, 1e-6)
    m_dot_fuel = m_dot_air / afr
    fuel_gps = m_dot_fuel * 1000.0

    power_kw = float(cycle.get("mean_power_hp", 0.0)) * 0.7457
    if power_kw <= 0.0:
        bsfc_gpkwh = None
    else:
        bsfc_gpkwh = fuel_gps * 3600.0 / power_kw

    return fuel_gps, bsfc_gpkwh


def run_partload_map(engine: Engine, rpm_grid: Iterable[float], throttle_grid: Iterable[float]) -> list[MapPoint]:
    points: list[MapPoint] = []
    rpm_values = [float(v) for v in rpm_grid]
    throttle_values = [float(v) for v in throttle_grid]

    for rpm in rpm_values:
        for throttle in throttle_values:
            local_engine = Engine.from_dict(engine.to_dict())
            local_engine.throttle.enabled = True
            local_engine.throttle.position = min(max(throttle, 0.0), 1.0)
            if local_engine.throttle.body_diam_m <= 0.0:
                local_engine.throttle.body_diam_m = local_engine.intake.throttle_body_dia * 1e-3

            sim = CylinderSimulator(local_engine)
            cycle = sim.run_cycle(rpm)
            map_est_kpa = cycle.get("map_est_kpa")
            fuel_gps, bsfc_gpkwh = _fuel_metrics(local_engine, cycle, map_est_kpa)

            points.append(
                MapPoint(
                    rpm=rpm,
                    throttle=throttle,
                    torque_nm=float(cycle["mean_torque_nm"]),
                    power_hp=float(cycle["mean_power_hp"]),
                    bmep_bar=float(cycle["bmep_bar"]),
                    ve_actual=float(cycle["ve_actual"]),
                    map_est_kpa=float(map_est_kpa) if map_est_kpa is not None else None,
                    fuel_gps=fuel_gps,
                    bsfc_gpkwh=bsfc_gpkwh,
                )
            )

    return points
