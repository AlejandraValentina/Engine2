"""Engine component data models for virtual dyno configuration.

This module defines core engine parts (block, head, cams, induction, exhaust,
forced-induction, and the root Engine container) with simple serialization
helpers for saving/loading JSON configurations.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import List, Optional

from core.units import cc_to_m3, mm_to_m


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

    return migrated


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
    artificial_diffusion: float = 0.0  # dimensionless scaling for numerical smoothing
    clamp_rho_min: float = 0.1  # kg/m^3
    clamp_p_min: float = 1e-6  # Pa
    clamp_p_max: float = 1e9  # Pa
    clamp_u_max: float = 1500.0  # m/s
    clamp_energy_max: float = 1.0e7  # J/m^3
    enable_heat_transfer_1d: bool = False
    wall_temperature_k: float = 450.0
    enable_0d_to_1d_exhaust_coupling: bool = False
    exhaust_valve_cd: float = 0.85
    exhaust_valve_area_model: str = "curtain"
    trace_metadata: bool = True

    def to_dict(self) -> dict:
        return {
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
            "artificial_diffusion": self.artificial_diffusion,
            "clamp_rho_min": self.clamp_rho_min,
            "clamp_p_min": self.clamp_p_min,
            "clamp_p_max": self.clamp_p_max,
            "clamp_u_max": self.clamp_u_max,
            "clamp_energy_max": self.clamp_energy_max,
            "enable_heat_transfer_1d": self.enable_heat_transfer_1d,
            "wall_temperature_k": self.wall_temperature_k,
            "enable_0d_to_1d_exhaust_coupling": self.enable_0d_to_1d_exhaust_coupling,
            "exhaust_valve_cd": self.exhaust_valve_cd,
            "exhaust_valve_area_model": self.exhaust_valve_area_model,
            "trace_metadata": self.trace_metadata,
        }

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
            artificial_diffusion=data.get("artificial_diffusion", 0.0),
            clamp_rho_min=data.get("clamp_rho_min", 0.1),
            clamp_p_min=data.get("clamp_p_min", 1e-6),
            clamp_p_max=data.get("clamp_p_max", 1e9),
            clamp_u_max=data.get("clamp_u_max", 1500.0),
            clamp_energy_max=data.get("clamp_energy_max", 1.0e7),
            enable_heat_transfer_1d=data.get("enable_heat_transfer_1d", False),
            wall_temperature_k=data.get("wall_temperature_k", 450.0),
            enable_0d_to_1d_exhaust_coupling=data.get("enable_0d_to_1d_exhaust_coupling", False),
            exhaust_valve_cd=data.get("exhaust_valve_cd", 0.85),
            exhaust_valve_area_model=data.get("exhaust_valve_area_model", "curtain"),
            trace_metadata=data.get("trace_metadata", True),
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

    def to_dict(self) -> dict:
        return {
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
        }

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
class Engine:
    schema_version: int = 1
    model_name: str = "Custom Engine"
    block: Block = field(default_factory=Block)
    head: CylinderHead = field(default_factory=CylinderHead)
    camshaft: Camshaft = field(default_factory=Camshaft)
    intake: IntakeSystem = field(default_factory=IntakeSystem)
    exhaust: ExhaustSystem = field(default_factory=ExhaustSystem)
    supercharger: Supercharger = field(default_factory=Supercharger)
    simulation_settings: SimulationSettings = field(default_factory=SimulationSettings)
    friction: Friction = field(default_factory=Friction)
    fuel: Fuel = field(default_factory=Fuel)
    combustion: Combustion = field(default_factory=Combustion)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "model_name": self.model_name,
            "block": self.block.to_dict(),
            "head": self.head.to_dict(),
            "camshaft": self.camshaft.to_dict(),
            "intake": self.intake.to_dict(),
            "exhaust": self.exhaust.to_dict(),
            "supercharger": self.supercharger.to_dict(),
            "simulation_settings": self.simulation_settings.to_dict(),
            "friction": self.friction.to_dict(),
            "fuel": self.fuel.to_dict(),
            "combustion": self.combustion.to_dict(),
        }

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
            supercharger=Supercharger.from_dict(migrated.get("supercharger", {})),
            simulation_settings=SimulationSettings.from_dict(migrated.get("simulation_settings", {})),
            friction=Friction.from_dict(migrated.get("friction", {})),
            fuel=Fuel.from_dict(migrated.get("fuel", {})),
            combustion=Combustion.from_dict(migrated.get("combustion", {})),
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
        if getattr(self.combustion, "thermal_efficiency", 0.5) <= 0.0:
            _fail("combustion.thermal_efficiency", "Combustion thermal efficiency must be positive")
        if getattr(self.fuel, "energy_density", 0.0) <= 0.0:
            _fail("fuel.energy_density", "Fuel energy density must be positive")
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

        return [msg for _path, msg in sorted(issues, key=lambda item: item[0])]

    def validate(self, strict: bool = False) -> bool:
        """Validate basic physical ranges; raise if strict and invalid."""
        issues = self.validate_with_issues()
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
    "Supercharger",
    "SimulationSettings",
    "Friction",
    "Fuel",
    "Combustion",
    "Engine",
]
