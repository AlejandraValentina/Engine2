"""Engine component data models for virtual dyno configuration.

This module defines core engine parts (block, head, cams, induction, exhaust,
forced-induction, and the root Engine container) with simple serialization
helpers for saving/loading JSON configurations.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, List, Optional

from core.preflight import collect_preflight_issues, collect_preflight_report
from core.units import cc_to_m3, mm_to_m


def _collect_leaf_paths(data: Any, prefix: str = "") -> set[str]:
    if not isinstance(data, dict):
        return {prefix} if prefix else set()

    paths: set[str] = set()
    for key, value in data.items():
        child = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            nested = _collect_leaf_paths(value, child)
            if nested:
                paths.update(nested)
            else:
                paths.add(child)
        else:
            paths.add(child)
    return paths


def _values_match(lhs: Any, rhs: Any) -> bool:
    try:
        return math.isclose(float(lhs), float(rhs), rel_tol=0.0, abs_tol=1e-9)
    except (TypeError, ValueError):
        return lhs == rhs


def migrate_preset_dict(data: dict) -> dict:
    """Normalize preset dictionaries for backward compatibility.

    - Adds missing schema_version/model_name fields with safe defaults.
    - Lifts legacy "cam" payloads into "camshaft" if present.
    """

    if not isinstance(data, dict):
        return data

    migrated = dict(data)
    migrated.setdefault("schema_version", 1)
    migrated.setdefault("model_name", migrated.get("name", "Custom Engine"))

    if "camshaft" not in migrated and "cam" in migrated:
        migrated["camshaft"] = migrated["cam"]

    head = migrated.get("head")
    if isinstance(head, dict):
        head_payload = dict(head)
        if "intake_valve_diameter_mm" not in head_payload and "intake_valve_diameter" in head_payload:
            head_payload["intake_valve_diameter_mm"] = head_payload["intake_valve_diameter"]
        if "exhaust_valve_diameter_mm" not in head_payload and "exhaust_valve_diameter" in head_payload:
            head_payload["exhaust_valve_diameter_mm"] = head_payload["exhaust_valve_diameter"]
        migrated["head"] = head_payload

    sim = migrated.get("simulation_settings")
    if isinstance(sim, dict) and "ignition_timing_btdc" in sim:
        combustion = migrated.get("combustion")
        combustion_payload = dict(combustion) if isinstance(combustion, dict) else {}
        combustion_payload.setdefault("ignition_advance", sim["ignition_timing_btdc"])
        migrated["combustion"] = combustion_payload

    return migrated


def _collect_schema_warnings(raw: dict, migrated: dict) -> list[str]:
    warnings: list[str] = []

    def warn(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    head_raw = raw.get("head") if isinstance(raw.get("head"), dict) else {}
    intake_mm = head_raw.get("intake_valve_diameter_mm")
    intake_legacy = head_raw.get("intake_valve_diameter")
    if intake_mm is not None and intake_legacy is not None and not _values_match(intake_mm, intake_legacy):
        warn(
            "head.intake_valve_diameter_mm and head.intake_valve_diameter were both provided with different values. "
            "Quick Dyno now treats head.intake_valve_diameter_mm as canonical; remove the legacy alias."
        )

    exhaust_mm = head_raw.get("exhaust_valve_diameter_mm")
    exhaust_legacy = head_raw.get("exhaust_valve_diameter")
    if exhaust_mm is not None and exhaust_legacy is not None and not _values_match(exhaust_mm, exhaust_legacy):
        warn(
            "head.exhaust_valve_diameter_mm and head.exhaust_valve_diameter were both provided with different values. "
            "Quick Dyno now treats head.exhaust_valve_diameter_mm as canonical; remove the legacy alias."
        )

    sim_raw = raw.get("simulation_settings") if isinstance(raw.get("simulation_settings"), dict) else {}
    comb_raw = raw.get("combustion") if isinstance(raw.get("combustion"), dict) else {}
    if "ignition_timing_btdc" in sim_raw:
        if "ignition_advance" not in comb_raw:
            warn(
                "simulation_settings.ignition_timing_btdc was promoted to combustion.ignition_advance for compatibility. "
                "Define combustion.ignition_advance explicitly because Quick Dyno uses that field."
            )
        elif not _values_match(sim_raw.get("ignition_timing_btdc"), comb_raw.get("ignition_advance")):
            warn(
                "combustion.ignition_advance and simulation_settings.ignition_timing_btdc differ. "
                "Quick Dyno uses combustion.ignition_advance; keep the legacy timing field aligned or remove it."
            )

    fuel_raw = raw.get("fuel") if isinstance(raw.get("fuel"), dict) else {}
    sim_fuel_raw = sim_raw.get("fuel") if isinstance(sim_raw.get("fuel"), dict) else {}
    if sim_fuel_raw.get("enabled", False):
        if (
            "energy_density" in fuel_raw
            and "lhv_j_per_kg" in sim_fuel_raw
            and not _values_match(fuel_raw.get("energy_density"), sim_fuel_raw.get("lhv_j_per_kg"))
        ):
            warn(
                "fuel.energy_density and simulation_settings.fuel.lhv_j_per_kg differ while simulation_settings.fuel.enabled=true. "
                "Quick Dyno v1 uses the top-level fuel block; v2 uses simulation_settings.fuel."
            )
        if (
            "stoich_afr" in fuel_raw
            and "afr_stoich" in sim_fuel_raw
            and not _values_match(fuel_raw.get("stoich_afr"), sim_fuel_raw.get("afr_stoich"))
        ):
            warn(
                "fuel.stoich_afr and simulation_settings.fuel.afr_stoich differ while simulation_settings.fuel.enabled=true. "
                "Keep them aligned to avoid v1/v2 mismatches."
            )

    supercharger_raw = raw.get("supercharger") if isinstance(raw.get("supercharger"), dict) else {}
    turbo_raw = raw.get("turbo") if isinstance(raw.get("turbo"), dict) else {}
    if str(supercharger_raw.get("type", "NA")).strip().lower() == "turbo":
        warn(
            "supercharger.type='Turbo' is deprecated and ambiguous. Use the dedicated turbo block for turbocharged engines."
        )
    if turbo_raw.get("enabled") and float(supercharger_raw.get("boost_pressure_bar", 0.0) or 0.0) > 0.0:
        warn(
            "turbo.enabled=true while supercharger.boost_pressure_bar is also positive. Quick Dyno will use the turbo block only."
        )

    return warnings


@dataclass
class Block:
    bore: float = 86.0  # millimeters
    stroke: float = 86.0  # millimeters
    conrod_length: float = 143.0  # millimeters
    num_cylinders: int = 4
    config: str = "L"  # e.g., "L", "V"
    bank_angle: float = 0.0  # degrees, 0 for inline
    firing_order: List[int] = field(default_factory=lambda: [1, 3, 4, 2])
    redline_rpm: float = 8000.0

    @property
    def displacement_cc(self) -> float:
        """Return total displacement in cubic centimeters."""
        bore_m = mm_to_m(self.bore)
        stroke_m = mm_to_m(self.stroke)
        single_cyl_vol_m3 = math.pi * (bore_m**2) * stroke_m / 4.0
        total_vol_m3 = single_cyl_vol_m3 * self.num_cylinders
        return total_vol_m3 * 1e6  # convert m^3 to cc

    def to_dict(self) -> dict:
        return {
            "bore": self.bore,
            "stroke": self.stroke,
            "conrod_length": self.conrod_length,
            "num_cylinders": self.num_cylinders,
            "config": self.config,
            "bank_angle": self.bank_angle,
            "firing_order": list(self.firing_order),
            "redline_rpm": self.redline_rpm,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        return cls(
            bore=data.get("bore", 86.0),
            stroke=data.get("stroke", 86.0),
            conrod_length=data.get("conrod_length", 143.0),
            num_cylinders=data.get("num_cylinders", 4),
            config=data.get("config", "L"),
            bank_angle=data.get("bank_angle", 0.0),
            firing_order=data.get("firing_order", [1, 3, 4, 2]),
            redline_rpm=data.get("redline_rpm", 8000.0),
        )


@dataclass
class CylinderHead:
    compression_ratio: float = 10.5
    intake_valves: int = 2
    exhaust_valves: int = 2
    intake_valve_diameter: float = 35.0  # millimeters (legacy alias)
    exhaust_valve_diameter: float = 30.0  # millimeters (legacy alias)
    intake_valve_diameter_mm: float = 35.0  # millimeters
    exhaust_valve_diameter_mm: float = 30.0  # millimeters
    combustion_chamber_vol: Optional[float] = None  # cc override
    port_flow_cfm: float = 200.0  # peak flow at max lift @ 28" H2O per valve
    port_flow_efficiency: float = 0.65  # 0.1 (very restrictive) .. 1.0 (race)
    mach_tolerance: float = 0.75  # Mach index where choking begins
    exhaust_valve_cd: float = 0.85  # discharge coefficient for exhaust valves
    exhaust_valve_seat_diameter_mm: Optional[float] = None  # millimeters
    gasket_thickness_mm: float = 1.0
    gasket_bore_mm: float = 88.0
    deck_clearance_mm: float = 0.0
    piston_dome_cc: float = 0.0

    def __post_init__(self) -> None:
        # Keep legacy/non-legacy valve diameter fields in sync for backward compatibility.
        if self.intake_valve_diameter_mm is None:
            self.intake_valve_diameter_mm = self.intake_valve_diameter
        if self.intake_valve_diameter is None:
            self.intake_valve_diameter = self.intake_valve_diameter_mm

        if self.exhaust_valve_diameter_mm is None:
            self.exhaust_valve_diameter_mm = self.exhaust_valve_diameter
        if self.exhaust_valve_diameter is None:
            self.exhaust_valve_diameter = self.exhaust_valve_diameter_mm
        if self.exhaust_valve_seat_diameter_mm is None:
            self.exhaust_valve_seat_diameter_mm = self.exhaust_valve_diameter_mm

    def to_dict(self) -> dict:
        return {
            "compression_ratio": self.compression_ratio,
            "intake_valves": self.intake_valves,
            "exhaust_valves": self.exhaust_valves,
            "intake_valve_diameter": self.intake_valve_diameter,
            "exhaust_valve_diameter": self.exhaust_valve_diameter,
            "intake_valve_diameter_mm": self.intake_valve_diameter_mm,
            "exhaust_valve_diameter_mm": self.exhaust_valve_diameter_mm,
            "combustion_chamber_vol": self.combustion_chamber_vol,
            "port_flow_cfm": self.port_flow_cfm,
            "port_flow_efficiency": self.port_flow_efficiency,
            "mach_tolerance": self.mach_tolerance,
            "exhaust_valve_cd": self.exhaust_valve_cd,
            "exhaust_valve_seat_diameter_mm": self.exhaust_valve_seat_diameter_mm,
            "gasket_thickness_mm": self.gasket_thickness_mm,
            "gasket_bore_mm": self.gasket_bore_mm,
            "deck_clearance_mm": self.deck_clearance_mm,
            "piston_dome_cc": self.piston_dome_cc,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CylinderHead":
        intake_dia = data.get(
            "intake_valve_diameter_mm",
            data.get("intake_valve_diameter", 35.0),
        )
        exhaust_dia = data.get(
            "exhaust_valve_diameter_mm",
            data.get("exhaust_valve_diameter", 30.0),
        )
        exhaust_seat = data.get("exhaust_valve_seat_diameter_mm", exhaust_dia)
        return cls(
            compression_ratio=data.get("compression_ratio", 10.5),
            intake_valves=data.get("intake_valves", 2),
            exhaust_valves=data.get("exhaust_valves", 2),
            intake_valve_diameter=intake_dia,
            exhaust_valve_diameter=exhaust_dia,
            intake_valve_diameter_mm=intake_dia,
            exhaust_valve_diameter_mm=exhaust_dia,
            combustion_chamber_vol=data.get("combustion_chamber_vol"),
            port_flow_cfm=data.get("port_flow_cfm", 200.0),
            port_flow_efficiency=data.get("port_flow_efficiency", 0.65),
            mach_tolerance=data.get("mach_tolerance", 0.75),
            exhaust_valve_cd=data.get("exhaust_valve_cd", 0.85),
            exhaust_valve_seat_diameter_mm=exhaust_seat,
            gasket_thickness_mm=data.get("gasket_thickness_mm", 1.0),
            gasket_bore_mm=data.get("gasket_bore_mm", 88.0),
            deck_clearance_mm=data.get("deck_clearance_mm", 0.0),
            piston_dome_cc=data.get("piston_dome_cc", 0.0),
        )


@dataclass
class Pipe:
    """Representation of a duct segment used in intake or exhaust systems."""

    length: float = 500.0  # millimeters
    diameter_inlet: float = 45.0  # millimeters
    diameter_outlet: float = 45.0  # millimeters
    wall_temperature: float = 600.0
    friction_coeff: float = 0.02

    def to_dict(self) -> dict:
        return {
            "length": self.length,
            "diameter_inlet": self.diameter_inlet,
            "diameter_outlet": self.diameter_outlet,
            "wall_temperature": self.wall_temperature,
            "friction_coeff": self.friction_coeff,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Pipe":
        return cls(
            length=data.get("length", 500.0),
            diameter_inlet=data.get("diameter_inlet", 45.0),
            diameter_outlet=data.get("diameter_outlet", 45.0),
            wall_temperature=data.get("wall_temperature", 600.0),
            friction_coeff=data.get("friction_coeff", 0.02),
        )


@dataclass
class Fuel:
    type_name: str = "Pump Gas"
    octane_rating: float = 93.0
    energy_density: float = 44e6  # J/kg
    stoich_afr: float = 14.7

    def to_dict(self) -> dict:
        return {
            "type_name": self.type_name,
            "octane_rating": self.octane_rating,
            "energy_density": self.energy_density,
            "stoich_afr": self.stoich_afr,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Fuel":
        return cls(
            type_name=data.get("type_name", "Pump Gas"),
            octane_rating=data.get("octane_rating", 93.0),
            energy_density=data.get("energy_density", 44e6),
            stoich_afr=data.get("stoich_afr", 14.7),
        )


@dataclass
class FuelConfig:
    enabled: bool = False
    mode: str = "lambda"
    lambda_target: float = 1.0
    afr_target: float = 14.7
    afr_stoich: float = 14.7
    lhv_j_per_kg: float = 4.3e7
    eta_comb: float = 0.98
    bsfc_units: str = "g_per_kwh"
    clamp_lambda_min: float = 0.6
    clamp_lambda_max: float = 2.0

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "lambda_target": self.lambda_target,
            "afr_target": self.afr_target,
            "afr_stoich": self.afr_stoich,
            "lhv_j_per_kg": self.lhv_j_per_kg,
            "eta_comb": self.eta_comb,
            "bsfc_units": self.bsfc_units,
            "clamp_lambda_min": self.clamp_lambda_min,
            "clamp_lambda_max": self.clamp_lambda_max,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FuelConfig":
        return cls(
            enabled=data.get("enabled", False),
            mode=data.get("mode", "lambda"),
            lambda_target=data.get("lambda_target", 1.0),
            afr_target=data.get("afr_target", 14.7),
            afr_stoich=data.get("afr_stoich", 14.7),
            lhv_j_per_kg=data.get("lhv_j_per_kg", 4.3e7),
            eta_comb=data.get("eta_comb", 0.98),
            bsfc_units=data.get("bsfc_units", "g_per_kwh"),
            clamp_lambda_min=data.get("clamp_lambda_min", 0.6),
            clamp_lambda_max=data.get("clamp_lambda_max", 2.0),
        )


@dataclass
class SpeciesConfig:
    enabled: bool = False
    model: str = "y_fresh"

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpeciesConfig":
        return cls(
            enabled=bool(data.get("enabled", False)),
            model=str(data.get("model", "y_fresh")),
        )


@dataclass
class WallThermalConfig:
    enabled: bool = False
    m_wall_kg: float = 1.0
    cp_wall_j_per_kgk: float = 500.0
    h_w_per_m2k: float = 50.0
    h_model: str = "constant"
    h_mult: float = 1.0
    h_min: float = 10.0
    h_max: float = 5000.0
    mu_model: str = "constant"
    mu_const: float = 1.8e-5
    k_th_const: float = 0.026
    pr_const: float = 0.71
    area_m2: float = 1.0
    twall_init_k: float = 450.0
    twall_min_k: float = 200.0
    twall_max_k: float = 1200.0

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "m_wall_kg": self.m_wall_kg,
            "cp_wall_j_per_kgk": self.cp_wall_j_per_kgk,
            "h_w_per_m2k": self.h_w_per_m2k,
            "h_model": self.h_model,
            "h_mult": self.h_mult,
            "h_min": self.h_min,
            "h_max": self.h_max,
            "mu_model": self.mu_model,
            "mu_const": self.mu_const,
            "k_th_const": self.k_th_const,
            "pr_const": self.pr_const,
            "area_m2": self.area_m2,
            "twall_init_k": self.twall_init_k,
            "twall_min_k": self.twall_min_k,
            "twall_max_k": self.twall_max_k,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WallThermalConfig":
        h_default = data.get("h_w_per_m2k", data.get("h_const", 50.0))
        return cls(
            enabled=bool(data.get("enabled", False)),
            m_wall_kg=float(data.get("m_wall_kg", 1.0)),
            cp_wall_j_per_kgk=float(data.get("cp_wall_j_per_kgk", 500.0)),
            h_w_per_m2k=float(h_default),
            h_model=str(data.get("h_model", "constant")),
            h_mult=float(data.get("h_mult", 1.0)),
            h_min=float(data.get("h_min", 10.0)),
            h_max=float(data.get("h_max", 5000.0)),
            mu_model=str(data.get("mu_model", "constant")),
            mu_const=float(data.get("mu_const", 1.8e-5)),
            k_th_const=float(data.get("k_th_const", 0.026)),
            pr_const=float(data.get("pr_const", 0.71)),
            area_m2=float(data.get("area_m2", 1.0)),
            twall_init_k=float(data.get("twall_init_k", 450.0)),
            twall_min_k=float(data.get("twall_min_k", 200.0)),
            twall_max_k=float(data.get("twall_max_k", 1200.0)),
        )


@dataclass
class SimulationSettings:
    """Simulation-level tunables such as ignition timing."""

    ignition_timing_btdc: float = 30.0  # degrees before TDC firing
    heat_loss_factor: float = 1.0  # scales Woschni heat loss
    pipe_friction_factor: float = 1.0  # scales L/D pipe friction penalty
    tuning_sensitivity: float = 1.0  # scales wave/resonance boosts
    air_temperature_c: float = 25.0  # ambient intake temperature
    air_pressure_bar: float = 1.013  # ambient pressure
    exhaust_backpressure_factor: float = 1.05  # heuristic exhaust absolute multiplier
    gamma_air: float = 1.40
    gamma_exhaust: float = 1.35
    gas_constant_R: float = 287.0  # J/(kg*K)
    cp_model: str = "constant"
    artificial_diffusion: float = 0.0  # dimensionless scaling for numerical smoothing
    clamp_rho_min: float = 0.1  # kg/m^3
    clamp_p_min: float = 1e-6  # Pa
    clamp_p_max: float = 1e9  # Pa
    clamp_u_max: float = 1500.0  # m/s
    clamp_energy_max: float = 1.0e7  # J/m^3
    enable_heat_transfer_1d: bool = False
    wall_temperature_k: float = 450.0
    wall_thermal: WallThermalConfig = field(default_factory=WallThermalConfig)
    enable_0d_to_1d_exhaust_coupling: bool = False
    exhaust_valve_cd: float = 0.85
    exhaust_valve_area_model: str = "curtain"
    trace_metadata: bool = True
    fuel: FuelConfig = field(default_factory=FuelConfig)
    species: SpeciesConfig = field(default_factory=SpeciesConfig)
    intake_plenum: dict[str, Any] = field(default_factory=dict)
    exhaust_plenum: dict[str, Any] = field(default_factory=dict)
    junction_capacitance: dict[str, Any] = field(default_factory=dict)
    junction_losses: dict[str, Any] = field(default_factory=dict)
    shock_cfl: dict[str, Any] = field(default_factory=dict)
    intake_coupling: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "ignition_timing_btdc": self.ignition_timing_btdc,
            "heat_loss_factor": self.heat_loss_factor,
            "pipe_friction_factor": self.pipe_friction_factor,
            "tuning_sensitivity": self.tuning_sensitivity,
            "air_temperature_c": self.air_temperature_c,
            "air_pressure_bar": self.air_pressure_bar,
            "exhaust_backpressure_factor": self.exhaust_backpressure_factor,
            "gamma_air": self.gamma_air,
            "gamma_exhaust": self.gamma_exhaust,
            "gas_constant_R": self.gas_constant_R,
            "cp_model": self.cp_model,
            "artificial_diffusion": self.artificial_diffusion,
            "clamp_rho_min": self.clamp_rho_min,
            "clamp_p_min": self.clamp_p_min,
            "clamp_p_max": self.clamp_p_max,
            "clamp_u_max": self.clamp_u_max,
            "clamp_energy_max": self.clamp_energy_max,
            "enable_heat_transfer_1d": self.enable_heat_transfer_1d,
            "wall_temperature_k": self.wall_temperature_k,
            "wall_thermal": self.wall_thermal.to_dict(),
            "enable_0d_to_1d_exhaust_coupling": self.enable_0d_to_1d_exhaust_coupling,
            "exhaust_valve_cd": self.exhaust_valve_cd,
            "exhaust_valve_area_model": self.exhaust_valve_area_model,
            "trace_metadata": self.trace_metadata,
            "fuel": self.fuel.to_dict(),
            "intake_plenum": self.intake_plenum,
            "exhaust_plenum": self.exhaust_plenum,
            "junction_capacitance": self.junction_capacitance,
            "junction_losses": self.junction_losses,
            "shock_cfl": self.shock_cfl,
            "intake_coupling": self.intake_coupling,
        }
        if self.species.enabled or self.species.model != "y_fresh":
            payload["species"] = self.species.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationSettings":
        return cls(
            ignition_timing_btdc=data.get("ignition_timing_btdc", 30.0),
            heat_loss_factor=data.get("heat_loss_factor", 1.0),
            pipe_friction_factor=data.get("pipe_friction_factor", 1.0),
            tuning_sensitivity=data.get("tuning_sensitivity", 1.0),
            air_temperature_c=data.get("air_temperature_c", 25.0),
            air_pressure_bar=data.get("air_pressure_bar", 1.013),
            exhaust_backpressure_factor=data.get("exhaust_backpressure_factor", 1.05),
            gamma_air=data.get("gamma_air", 1.40),
            gamma_exhaust=data.get("gamma_exhaust", 1.35),
            gas_constant_R=data.get("gas_constant_R", 287.0),
            cp_model=data.get("cp_model", "constant"),
            artificial_diffusion=data.get("artificial_diffusion", 0.0),
            clamp_rho_min=data.get("clamp_rho_min", 0.1),
            clamp_p_min=data.get("clamp_p_min", 1e-6),
            clamp_p_max=data.get("clamp_p_max", 1e9),
            clamp_u_max=data.get("clamp_u_max", 1500.0),
            clamp_energy_max=data.get("clamp_energy_max", 1.0e7),
            enable_heat_transfer_1d=data.get("enable_heat_transfer_1d", False),
            wall_temperature_k=data.get("wall_temperature_k", 450.0),
            wall_thermal=WallThermalConfig.from_dict(data.get("wall_thermal", {})),
            enable_0d_to_1d_exhaust_coupling=data.get("enable_0d_to_1d_exhaust_coupling", False),
            exhaust_valve_cd=data.get("exhaust_valve_cd", 0.85),
            exhaust_valve_area_model=data.get("exhaust_valve_area_model", "curtain"),
            trace_metadata=data.get("trace_metadata", True),
            fuel=FuelConfig.from_dict(data.get("fuel", {})),
            species=SpeciesConfig.from_dict(data.get("species", {})),
            intake_plenum=data.get("intake_plenum", {}),
            exhaust_plenum=data.get("exhaust_plenum", {}),
            junction_capacitance=data.get("junction_capacitance", {}),
            junction_losses=data.get("junction_losses", {}),
            shock_cfl=data.get("shock_cfl", {}),
            intake_coupling=data.get("intake_coupling", {}),
        )


@dataclass
class Combustion:
    thermal_efficiency: float = 0.50  # 0.3 .. 0.7
    burn_duration: float = 50.0  # crank degrees
    ignition_advance: float = 30.0  # degrees BTDC
    target_ca50_deg_atdc: Optional[float] = None
    use_dynamic_burn_duration: bool = False
    use_dynamic_ca50: bool = False
    burn_duration_base: float = 50.0
    burn_duration_rpm_factor: float = 0.0
    burn_duration_load_factor: float = 0.0
    ca50_base_deg_atdc: float = 8.0
    ca50_rpm_factor: float = 0.0
    ca50_load_factor: float = 0.0
    afr: float = 13.0  # air-fuel ratio
    chamber_type: str = "Modern Pentroof"
    wiebe_a: float = 5.0
    wiebe_m: float = 2.0
    residual_coupling: dict[str, Any] = field(default_factory=dict)
    adaptive_model: dict[str, Any] = field(default_factory=dict)
    wiebe: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "thermal_efficiency": self.thermal_efficiency,
            "burn_duration": self.burn_duration,
            "ignition_advance": self.ignition_advance,
            "target_ca50_deg_atdc": self.target_ca50_deg_atdc,
            "use_dynamic_burn_duration": self.use_dynamic_burn_duration,
            "use_dynamic_ca50": self.use_dynamic_ca50,
            "burn_duration_base": self.burn_duration_base,
            "burn_duration_rpm_factor": self.burn_duration_rpm_factor,
            "burn_duration_load_factor": self.burn_duration_load_factor,
            "ca50_base_deg_atdc": self.ca50_base_deg_atdc,
            "ca50_rpm_factor": self.ca50_rpm_factor,
            "ca50_load_factor": self.ca50_load_factor,
            "afr": self.afr,
            "chamber_type": self.chamber_type,
            "wiebe_a": self.wiebe_a,
            "wiebe_m": self.wiebe_m,
            "residual_coupling": self.residual_coupling,
            "adaptive_model": self.adaptive_model,
        }
        if self.wiebe:
            payload["wiebe"] = self.wiebe
        return payload

    @classmethod
    def from_dict(cls, data: dict) -> "Combustion":
        return cls(
            thermal_efficiency=data.get("thermal_efficiency", 0.50),
            burn_duration=data.get("burn_duration", 50.0),
            ignition_advance=data.get("ignition_advance", 30.0),
            target_ca50_deg_atdc=data.get("target_ca50_deg_atdc"),
            use_dynamic_burn_duration=data.get("use_dynamic_burn_duration", False),
            use_dynamic_ca50=data.get("use_dynamic_ca50", False),
            burn_duration_base=data.get("burn_duration_base", 50.0),
            burn_duration_rpm_factor=data.get("burn_duration_rpm_factor", 0.0),
            burn_duration_load_factor=data.get("burn_duration_load_factor", 0.0),
            ca50_base_deg_atdc=data.get("ca50_base_deg_atdc", 8.0),
            ca50_rpm_factor=data.get("ca50_rpm_factor", 0.0),
            ca50_load_factor=data.get("ca50_load_factor", 0.0),
            afr=data.get("afr", 13.0),
            chamber_type=data.get("chamber_type", "Modern Pentroof"),
            wiebe_a=data.get("wiebe_a", 5.0),
            wiebe_m=data.get("wiebe_m", 2.0),
            residual_coupling=data.get("residual_coupling", {}),
            adaptive_model=data.get("adaptive_model", {}),
            wiebe=data.get("wiebe", {}),
        )


@dataclass
class Camshaft:
    intake_lift: float = 10.0  # millimeters
    exhaust_lift: float = 10.0  # millimeters
    intake_duration: float = 260.0  # degrees
    exhaust_duration: float = 260.0  # degrees
    lobe_separation: float = 110.0  # degrees
    advance: float = 0.0  # degrees
    peak_rpm: float = 5500.0  # rpm where cam is tuned to breathe best
    phase_deg_intake: float = 0.0  # degrees
    phase_deg_exhaust: float = 0.0  # degrees

    def get_lift(self, angle_deg: float, intake: bool = True) -> float:
        """Approximate valve lift (mm) at a given crank angle using harmonic profile.

        Intake and exhaust lobes are centered independently:
        - Intake center at (lobe_separation - advance) degrees ATDC firing.
        - Exhaust center at (720 - (lobe_separation + advance)) degrees BTDC.

        Angles wrap over 0–720° and the lift shape is a cosine-squared arc.
        Phase offsets shift the cam event by subtracting the phase before wrap.
        """
        duration = self.intake_duration if intake else self.exhaust_duration
        max_lift = self.intake_lift if intake else self.exhaust_lift
        phase_deg = self.phase_deg_intake if intake else self.phase_deg_exhaust

        center_intake = self.lobe_separation - self.advance
        center_exhaust = 720.0 - (self.lobe_separation + self.advance)
        center = center_intake if intake else center_exhaust

        span = duration
        start = center - span / 2.0
        start_mod = start % 720.0
        angle = (angle_deg - phase_deg) % 720.0

        if span >= 720.0:
            phase = 0.5
        else:
            end_mod = (start_mod + span) % 720.0
            if start_mod <= end_mod:
                active = start_mod <= angle <= end_mod
                rel = angle - start_mod if active else -1.0
            else:
                active = angle >= start_mod or angle <= end_mod
                rel = (angle - start_mod) % 720.0 if active else -1.0
            if not active:
                return 0.0
            phase = rel / span

        return max_lift * (math.sin(math.pi * phase)) ** 2

    def to_dict(self) -> dict:
        return {
            "intake_lift": self.intake_lift,
            "exhaust_lift": self.exhaust_lift,
            "intake_duration": self.intake_duration,
            "exhaust_duration": self.exhaust_duration,
            "lobe_separation": self.lobe_separation,
            "advance": self.advance,
            "peak_rpm": self.peak_rpm,
            "phase_deg_intake": self.phase_deg_intake,
            "phase_deg_exhaust": self.phase_deg_exhaust,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Camshaft":
        return cls(
            intake_lift=data.get("intake_lift", 10.0),
            exhaust_lift=data.get("exhaust_lift", 10.0),
            intake_duration=data.get("intake_duration", 260.0),
            exhaust_duration=data.get("exhaust_duration", 260.0),
            lobe_separation=data.get("lobe_separation", 110.0),
            advance=data.get("advance", 0.0),
            peak_rpm=data.get("peak_rpm", 5500.0),
            phase_deg_intake=data.get("phase_deg_intake", 0.0),
            phase_deg_exhaust=data.get("phase_deg_exhaust", 0.0),
        )


@dataclass
class Friction:
    """Parameterized FMEP curve: kPa = A + B*rpm + C*rpm^2."""
    bottom_end_type: str = "Standard"  # "Standard", "Performance", "Race"
    water_pump: bool = True
    alternator: bool = True
    power_steering: bool = True
    mechanical_fan: bool = False
    friction_base_kpa: float = 35.0
    friction_linear_factor: float = 0.02
    friction_quadratic_factor: float = 1.8e-6
    global_scaling_factor: float = 1.0

    def to_dict(self) -> dict:
        return {
            "bottom_end_type": self.bottom_end_type,
            "water_pump": self.water_pump,
            "alternator": self.alternator,
            "power_steering": self.power_steering,
            "mechanical_fan": self.mechanical_fan,
            "friction_base_kpa": self.friction_base_kpa,
            "friction_linear_factor": self.friction_linear_factor,
            "friction_quadratic_factor": self.friction_quadratic_factor,
            "global_scaling_factor": self.global_scaling_factor,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Friction":
        return cls(
            bottom_end_type=data.get("bottom_end_type", "Standard"),
            water_pump=data.get("water_pump", True),
            alternator=data.get("alternator", True),
            power_steering=data.get("power_steering", True),
            mechanical_fan=data.get("mechanical_fan", False),
            friction_base_kpa=data.get("friction_base_kpa", 35.0),
            friction_linear_factor=data.get("friction_linear_factor", 0.02),
            friction_quadratic_factor=data.get("friction_quadratic_factor", 1.8e-6),
            global_scaling_factor=data.get("global_scaling_factor", 1.0),
        )


@dataclass
class IntakeSystem:
    runner_length: float = 300.0  # millimeters
    runner_diameter: float = 45.0  # millimeters
    plenum_volume: float = 3.0  # liters
    throttle_body_dia: float = 70.0  # millimeters
    throttle_cfm: float = 500.0  # carb/throttle flow rating
    flow_loss_coefficient: float = 0.0  # additional restriction factor

    def to_dict(self) -> dict:
        return {
            "runner_length": self.runner_length,
            "runner_diameter": self.runner_diameter,
            "plenum_volume": self.plenum_volume,
            "throttle_body_dia": self.throttle_body_dia,
            "throttle_cfm": self.throttle_cfm,
            "flow_loss_coefficient": self.flow_loss_coefficient,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IntakeSystem":
        return cls(
            runner_length=data.get("runner_length", 300.0),
            runner_diameter=data.get("runner_diameter", 45.0),
            plenum_volume=data.get("plenum_volume", 3.0),
            throttle_body_dia=data.get("throttle_body_dia", 70.0),
            throttle_cfm=data.get("throttle_cfm", 500.0),
            flow_loss_coefficient=data.get("flow_loss_coefficient", 0.0),
        )


@dataclass
class Throttle:
    enabled: bool = False
    position: float = 1.0
    body_diam_m: float = 0.0
    cd: float = 1.0
    area_exponent: float = 2.0
    rate_limit_per_s: float | None = None
    safety_clamps: bool = False
    p0_amb_Pa: float | None = None
    T0_amb_K: float | None = None
    Y0_amb: float | None = None

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "position": self.position,
            "body_diam_m": self.body_diam_m,
            "cd": self.cd,
            "area_exponent": self.area_exponent,
            "rate_limit_per_s": self.rate_limit_per_s,
            "safety_clamps": self.safety_clamps,
            "p0_amb_Pa": self.p0_amb_Pa,
            "T0_amb_K": self.T0_amb_K,
            "Y0_amb": self.Y0_amb,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Throttle":
        rate_limit = data.get("rate_limit_per_s")
        return cls(
            enabled=bool(data.get("enabled", False)),
            position=float(data.get("position", 1.0)),
            body_diam_m=float(data.get("body_diam_m", 0.0)),
            cd=float(data.get("cd", 1.0)),
            area_exponent=float(data.get("area_exponent", 2.0)),
            rate_limit_per_s=float(rate_limit) if rate_limit is not None else None,
            safety_clamps=bool(data.get("safety_clamps", False)),
            p0_amb_Pa=data.get("p0_amb_Pa"),
            T0_amb_K=data.get("T0_amb_K"),
            Y0_amb=data.get("Y0_amb"),
        )


@dataclass
class ExhaustSystem:
    header_primary_length: float = 400.0  # millimeters
    header_primary_diameter: float = 38.0  # millimeters
    collector_length: float = 500.0  # millimeters

    def to_dict(self) -> dict:
        return {
            "header_primary_length": self.header_primary_length,
            "header_primary_diameter": self.header_primary_diameter,
            "collector_length": self.collector_length,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExhaustSystem":
        return cls(
            header_primary_length=data.get("header_primary_length", 400.0),
            header_primary_diameter=data.get("header_primary_diameter", 38.0),
            collector_length=data.get("collector_length", 500.0),
        )


@dataclass
class Supercharger:
    type: str = "NA"  # "NA", "Turbo", "Roots"
    boost_pressure_bar: float = 0.0
    intercooler_efficiency: float = 0.70

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "boost_pressure_bar": self.boost_pressure_bar,
            "intercooler_efficiency": self.intercooler_efficiency,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Supercharger":
        return cls(
            type=data.get("type", "NA"),
            boost_pressure_bar=data.get("boost_pressure_bar", 0.0),
            intercooler_efficiency=data.get("intercooler_efficiency", 0.70),
        )


@dataclass
class Turbo:
    enabled: bool = False
    compressor_map: list[dict] = field(default_factory=list)
    turbine_map: list[dict] = field(default_factory=list)
    compressor_efficiency: float = 0.7
    turbine_efficiency: float = 0.7
    target_boost_kpa: float | None = None
    target_pr: float | None = None
    wastegate_enabled: bool = True
    wastegate_gain: float = 0.5
    max_iters: int = 8
    intercooler_efficiency: float = 0.6
    response_model: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "compressor_map": self.compressor_map,
            "turbine_map": self.turbine_map,
            "compressor_efficiency": self.compressor_efficiency,
            "turbine_efficiency": self.turbine_efficiency,
            "target_boost_kpa": self.target_boost_kpa,
            "target_pr": self.target_pr,
            "wastegate_enabled": self.wastegate_enabled,
            "wastegate_gain": self.wastegate_gain,
            "max_iters": self.max_iters,
            "intercooler_efficiency": self.intercooler_efficiency,
            "response_model": self.response_model,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Turbo":
        return cls(
            enabled=bool(data.get("enabled", False)),
            compressor_map=list(data.get("compressor_map", [])),
            turbine_map=list(data.get("turbine_map", [])),
            compressor_efficiency=float(data.get("compressor_efficiency", 0.7)),
            turbine_efficiency=float(data.get("turbine_efficiency", 0.7)),
            target_boost_kpa=data.get("target_boost_kpa"),
            target_pr=data.get("target_pr"),
            wastegate_enabled=bool(data.get("wastegate_enabled", True)),
            wastegate_gain=float(data.get("wastegate_gain", 0.5)),
            max_iters=int(data.get("max_iters", 8)),
            intercooler_efficiency=float(data.get("intercooler_efficiency", 0.6)),
            response_model=data.get("response_model", {}),
        )


@dataclass
class Engine:
    schema_version: int = 1
    model_name: str = "Custom Engine"
    block: Block = field(default_factory=Block)
    head: CylinderHead = field(default_factory=CylinderHead)
    camshaft: Camshaft = field(default_factory=Camshaft)
    intake: IntakeSystem = field(default_factory=IntakeSystem)
    exhaust: ExhaustSystem = field(default_factory=ExhaustSystem)
    throttle: Throttle = field(default_factory=Throttle)
    supercharger: Supercharger = field(default_factory=Supercharger)
    turbo: Turbo = field(default_factory=Turbo)
    simulation_settings: SimulationSettings = field(default_factory=SimulationSettings)
    friction: Friction = field(default_factory=Friction)
    fuel: Fuel = field(default_factory=Fuel)
    combustion: Combustion = field(default_factory=Combustion)
    provided_fields: set[str] | None = field(default=None, repr=False, compare=False)
    schema_warnings: list[str] = field(default_factory=list, repr=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "model_name": self.model_name,
            "block": self.block.to_dict(),
            "head": self.head.to_dict(),
            "camshaft": self.camshaft.to_dict(),
            "intake": self.intake.to_dict(),
            "exhaust": self.exhaust.to_dict(),
            "throttle": self.throttle.to_dict(),
            "supercharger": self.supercharger.to_dict(),
            "turbo": self.turbo.to_dict(),
            "simulation_settings": self.simulation_settings.to_dict(),
            "friction": self.friction.to_dict(),
            "fuel": self.fuel.to_dict(),
            "combustion": self.combustion.to_dict(),
        }

    def induction_classification(self) -> str:
        """Return the canonical UI/validation induction classification.

        Priority is intentionally exact:
        1. turbo.enabled => "Turbo"
        2. turbo disabled and supercharger.type != "NA" => "Supercharger"
        3. otherwise => "NA"
        """

        if bool(getattr(self.turbo, "enabled", False)):
            return "Turbo"
        supercharger_type = str(getattr(self.supercharger, "type", "NA") or "NA")
        if supercharger_type != "NA":
            return "Supercharger"
        return "NA"

    def induction_mode_name(self) -> str:
        classification = self.induction_classification()
        if classification == "Turbo":
            return "Turbo"
        if classification == "Supercharger":
            supercharger_type = str(getattr(self.supercharger, "type", "Supercharger") or "Supercharger").strip()
            if not supercharger_type or supercharger_type == "NA":
                return "Supercharger"
            return supercharger_type
        return "Naturally Aspirated"

    def induction_summary(self) -> str:
        classification = self.induction_classification()
        if classification == "Turbo":
            target_boost_kpa = getattr(self.turbo, "target_boost_kpa", None)
            target_pr = getattr(self.turbo, "target_pr", None)
            if target_boost_kpa is not None:
                return f"Turbo @ {float(target_boost_kpa):.0f} kPa target"
            if target_pr is not None:
                return f"Turbo @ PR {float(target_pr):.2f}"
            return "Turbo"
        if classification == "Supercharger":
            supercharger_name = self.induction_mode_name()
            boost_bar = float(getattr(self.supercharger, "boost_pressure_bar", 0.0) or 0.0)
            if boost_bar > 0.0:
                return f"{supercharger_name} @ {boost_bar:.2f} bar"
            return supercharger_name
        return "Naturally Aspirated"

    def induction_tree_label(self) -> str:
        return f"Induction System ({self.induction_mode_name()})"

    def set_induction_mode(self, mode: str) -> None:
        normalized = str(mode or "NA").strip().lower()
        if normalized in {"na", "naturally aspirated", "naturally_aspirated"}:
            self.turbo.enabled = False
            self.supercharger.type = "NA"
            self.supercharger.boost_pressure_bar = 0.0
            return

        if normalized == "turbo":
            self.turbo.enabled = True
            self.supercharger.type = "NA"
            self.supercharger.boost_pressure_bar = 0.0
            return

        self.turbo.enabled = False
        self.supercharger.type = str(mode).strip() or "Roots"

    @classmethod
    def from_dict(cls, data: dict) -> "Engine":
        migrated = migrate_preset_dict(data)
        cam_data = migrated.get("camshaft") or migrated.get("cam") or {}
        return cls(
            schema_version=migrated.get("schema_version", 1),
            model_name=migrated.get("model_name", "Custom Engine"),
            block=Block.from_dict(migrated.get("block", {})),
            head=CylinderHead.from_dict(migrated.get("head", {})),
            camshaft=Camshaft.from_dict(cam_data),
            intake=IntakeSystem.from_dict(migrated.get("intake", {})),
            exhaust=ExhaustSystem.from_dict(migrated.get("exhaust", {})),
            throttle=Throttle.from_dict(migrated.get("throttle", {})),
            supercharger=Supercharger.from_dict(migrated.get("supercharger", {})),
            turbo=Turbo.from_dict(migrated.get("turbo", {})),
            simulation_settings=SimulationSettings.from_dict(migrated.get("simulation_settings", {})),
            friction=Friction.from_dict(migrated.get("friction", {})),
            fuel=Fuel.from_dict(migrated.get("fuel", {})),
            combustion=Combustion.from_dict(migrated.get("combustion", {})),
            provided_fields=_collect_leaf_paths(migrated),
            schema_warnings=_collect_schema_warnings(data if isinstance(data, dict) else {}, migrated),
        )

    def save_to_file(self, filename: str) -> None:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def validate_with_issues(self) -> list[str]:
        """Return a list of validation issues without raising."""
        issues: list[tuple[str, str]] = []

        def _fail(path: str, msg: str) -> None:
            issues.append((path, msg))

        if self.block.bore <= 0 or self.block.stroke <= 0 or self.block.conrod_length <= 0:
            _fail("block.geometry", "Block geometry must be positive (bore/stroke/conrod)")
        if self.block.num_cylinders < 1:
            _fail("block.num_cylinders", "Engine must have at least one cylinder")
        if self.head.compression_ratio <= 1.0:
            _fail("head.compression_ratio", "Compression ratio must exceed 1.0")
        if getattr(self.head, "port_flow_cfm", 0.0) < 0.0:
            _fail("head.port_flow_cfm", "Port flow CFM must be non-negative")
        throttle_cfm = getattr(self.intake, "throttle_cfm", None)
        throttle_flow_cfm = getattr(self.intake, "throttle_flow_cfm", None)
        if throttle_cfm is not None and throttle_cfm < 0:
            _fail("intake.throttle_cfm", "Throttle CFM must be non-negative")
        if throttle_flow_cfm is not None and throttle_flow_cfm < 0:
            _fail("intake.throttle_flow_cfm", "Throttle flow CFM must be non-negative")
        if getattr(self.intake, "runner_length", 1.0) <= 0.0 or getattr(self.intake, "runner_diameter", 1.0) <= 0.0:
            _fail("intake.geometry", "Intake runner geometry must be positive")
        throttle = getattr(self, "throttle", None)
        if throttle is not None and getattr(throttle, "enabled", False):
            if not (0.0 <= float(throttle.position) <= 1.0):
                _fail("throttle.position", "Throttle position must be within [0, 1]")
            if float(throttle.body_diam_m) <= 0.0:
                _fail("throttle.body_diam_m", "Throttle body diameter must be positive when enabled")
            if float(throttle.cd) <= 0.0:
                _fail("throttle.cd", "Throttle Cd must be positive")
            if float(throttle.area_exponent) <= 0.0:
                _fail("throttle.area_exponent", "Throttle area exponent must be positive")
        if getattr(self.combustion, "thermal_efficiency", 0.5) <= 0.0:
            _fail("combustion.thermal_efficiency", "Combustion thermal efficiency must be positive")
        adaptive_model = getattr(self.combustion, "adaptive_model", {}) or {}
        if adaptive_model:
            if not isinstance(adaptive_model, dict):
                _fail("combustion.adaptive_model", "Combustion adaptive_model must be an object")
            else:
                duration_min = float(adaptive_model.get("duration_min_deg", 10.0))
                duration_max = float(adaptive_model.get("duration_max_deg", 120.0))
                if duration_min <= 0.0:
                    _fail("combustion.adaptive_model.duration_min_deg", "Adaptive combustion duration_min_deg must be positive")
                if duration_max < duration_min:
                    _fail(
                        "combustion.adaptive_model.duration_max_deg",
                        "Adaptive combustion duration_max_deg must be >= duration_min_deg",
                    )
                ca50_min = float(adaptive_model.get("ca50_min_deg_atdc", -5.0))
                ca50_max = float(adaptive_model.get("ca50_max_deg_atdc", 40.0))
                if ca50_max < ca50_min:
                    _fail(
                        "combustion.adaptive_model.ca50_max_deg_atdc",
                        "Adaptive combustion ca50_max_deg_atdc must be >= ca50_min_deg_atdc",
                    )
                duration_scale = float(adaptive_model.get("duration_scale", 1.0))
                if duration_scale <= 0.0:
                    _fail("combustion.adaptive_model.duration_scale", "Adaptive combustion duration_scale must be positive")
        if getattr(self.fuel, "energy_density", 0.0) <= 0.0:
            _fail("fuel.energy_density", "Fuel energy density must be positive")
        turbo = getattr(self, "turbo", None)
        if turbo is not None:
            if float(getattr(turbo, "wastegate_gain", 0.0)) <= 0.0:
                _fail("turbo.wastegate_gain", "Turbo wastegate_gain must be positive")
            if int(getattr(turbo, "max_iters", 0)) < 1:
                _fail("turbo.max_iters", "Turbo max_iters must be >= 1")
            if not (0.0 <= float(getattr(turbo, "intercooler_efficiency", 0.0)) <= 1.0):
                _fail("turbo.intercooler_efficiency", "Turbo intercooler_efficiency must be within [0, 1]")
            response_model = getattr(turbo, "response_model", {}) or {}
            if response_model:
                if not isinstance(response_model, dict):
                    _fail("turbo.response_model", "Turbo response_model must be an object")
                else:
                    if bool(response_model.get("enabled", False)):
                        spool_width_rpm = float(response_model.get("spool_width_rpm", 800.0))
                        flow_width_kg_s = float(response_model.get("flow_width_kg_s", 0.04))
                        min_response = float(response_model.get("min_response", 0.25))
                        if spool_width_rpm <= 0.0:
                            _fail("turbo.response_model.spool_width_rpm", "Turbo response_model spool_width_rpm must be positive")
                        if flow_width_kg_s <= 0.0:
                            _fail("turbo.response_model.flow_width_kg_s", "Turbo response_model flow_width_kg_s must be positive")
                        if not (0.0 < min_response <= 1.0):
                            _fail("turbo.response_model.min_response", "Turbo response_model min_response must be within (0, 1]")
        fuel_cfg = getattr(self.simulation_settings, "fuel", None)
        if fuel_cfg is not None and getattr(fuel_cfg, "enabled", False):
            if getattr(fuel_cfg, "mode", "lambda") not in {"lambda", "afr"}:
                _fail("simulation_settings.fuel.mode", "Fuel mode must be 'lambda' or 'afr'")
            if getattr(fuel_cfg, "afr_stoich", 0.0) <= 0.0:
                _fail("simulation_settings.fuel.afr_stoich", "Fuel AFR stoich must be positive")
            if getattr(fuel_cfg, "lhv_j_per_kg", 0.0) <= 0.0:
                _fail("simulation_settings.fuel.lhv_j_per_kg", "Fuel LHV must be positive")
            if getattr(fuel_cfg, "eta_comb", 0.0) <= 0.0:
                _fail("simulation_settings.fuel.eta_comb", "Fuel eta_comb must be positive")
            if getattr(fuel_cfg, "clamp_lambda_min", 0.0) <= 0.0:
                _fail("simulation_settings.fuel.clamp_lambda_min", "Fuel clamp_lambda_min must be positive")
            clamp_max = getattr(fuel_cfg, "clamp_lambda_max", 0.0)
            if clamp_max <= 0.0:
                _fail("simulation_settings.fuel.clamp_lambda_max", "Fuel clamp_lambda_max must be positive")
            if clamp_max < getattr(fuel_cfg, "clamp_lambda_min", 0.0):
                _fail("simulation_settings.fuel.clamp_lambda_max", "Fuel clamp_lambda_max must be >= clamp_lambda_min")
            if getattr(fuel_cfg, "bsfc_units", "g_per_kwh") != "g_per_kwh":
                _fail("simulation_settings.fuel.bsfc_units", "Fuel bsfc_units must be 'g_per_kwh'")
        exhaust_cd = getattr(self.simulation_settings, "exhaust_valve_cd", None)
        if exhaust_cd is None:
            exhaust_cd = getattr(self.head, "exhaust_valve_cd", 0.85)
        if not (0.0 < float(exhaust_cd) <= 1.2):
            _fail("head.exhaust_valve_cd", "Exhaust valve Cd must be between 0 and 1.2")
        seat_mm = getattr(self.head, "exhaust_valve_seat_diameter_mm", self.head.exhaust_valve_diameter_mm)
        if seat_mm is None or seat_mm <= 0.0:
            _fail("head.exhaust_valve_seat_diameter_mm", "Exhaust valve seat diameter must be positive")
        if getattr(self.simulation_settings, "exhaust_valve_area_model", "curtain") not in {"curtain", "fixed"}:
            _fail(
                "simulation_settings.exhaust_valve_area_model",
                "Exhaust valve area model must be 'curtain' or 'fixed'",
            )
        cp_model = getattr(self.simulation_settings, "cp_model", "constant")
        if cp_model not in {"constant", "nasa7"}:
            _fail("simulation_settings.cp_model", "cp_model must be 'constant' or 'nasa7'")

        return [msg for _path, msg in sorted(issues, key=lambda item: item[0])]

    def was_field_explicitly_provided(self, path: str) -> bool:
        return self.provided_fields is not None and path in self.provided_fields

    def validate(self, strict: bool = False) -> bool:
        """Validate basic physical ranges; raise if strict and invalid."""
        issues = self.validate_with_issues()
        if issues and strict:
            raise ValueError("; ".join(issues))
        return not issues

    def preflight_validate_with_issues(self, operation: str = "dyno", mode: str = "v1") -> list[str]:
        issues = list(self.validate_with_issues())
        for issue in collect_preflight_issues(self, operation=operation, mode=mode):
            if issue not in issues:
                issues.append(issue)
        return issues

    def preflight_review(self, operation: str = "dyno", mode: str = "v1") -> dict[str, list[str]]:
        errors = list(self.validate_with_issues())
        report = collect_preflight_report(self, operation=operation, mode=mode)
        for issue in report["errors"]:
            if issue not in errors:
                errors.append(issue)
        return {"errors": errors, "warnings": report["warnings"]}

    def preflight_validate(self, operation: str = "dyno", mode: str = "v1", strict: bool = False) -> bool:
        issues = self.preflight_review(operation=operation, mode=mode)["errors"]
        if issues and strict:
            raise ValueError("; ".join(issues))
        return not issues

    @classmethod
    def load_from_file(cls, filename: str) -> "Engine":
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def calculate_geometric_cr(self) -> float:
        """Compute geometric compression ratio using gasket/deck/dome data."""
        bore_m = self.block.bore * 1e-3
        stroke_m = self.block.stroke * 1e-3
        area_m2 = math.pi * (bore_m**2) / 4.0
        V_swept = area_m2 * stroke_m

        head = self.head
        gasket_bore_m = head.gasket_bore_mm * 1e-3
        gasket_thickness_m = head.gasket_thickness_mm * 1e-3
        deck_clearance_m = head.deck_clearance_mm * 1e-3

        V_gasket = math.pi * (gasket_bore_m**2) * gasket_thickness_m / 4.0
        V_deck = area_m2 * deck_clearance_m

        if head.combustion_chamber_vol is not None:
            V_chamber = cc_to_m3(head.combustion_chamber_vol)
        elif head.compression_ratio > 1.0:
            V_chamber = V_swept / (head.compression_ratio - 1.0)
        else:
            return 0.0

        V_total_clearance = V_chamber + V_gasket + V_deck - cc_to_m3(head.piston_dome_cc)
        if V_total_clearance <= 0.0:
            return 0.0

        return (V_swept + V_total_clearance) / V_total_clearance


__all__ = [
    "Block",
    "CylinderHead",
    "Pipe",
    "Camshaft",
    "IntakeSystem",
    "ExhaustSystem",
    "Throttle",
    "Supercharger",
    "SimulationSettings",
    "Friction",
    "Fuel",
    "FuelConfig",
    "SpeciesConfig",
    "Combustion",
    "Engine",
]
