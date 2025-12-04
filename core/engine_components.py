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
        bore_m = self.bore * 1e-3
        stroke_m = self.stroke * 1e-3
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
            gasket_thickness_mm=data.get("gasket_thickness_mm", 1.0),
            gasket_bore_mm=data.get("gasket_bore_mm", 88.0),
            deck_clearance_mm=data.get("deck_clearance_mm", 0.0),
            piston_dome_cc=data.get("piston_dome_cc", 0.0),
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

    def to_dict(self) -> dict:
        return {
            "ignition_timing_btdc": self.ignition_timing_btdc,
            "heat_loss_factor": self.heat_loss_factor,
            "pipe_friction_factor": self.pipe_friction_factor,
            "tuning_sensitivity": self.tuning_sensitivity,
            "air_temperature_c": self.air_temperature_c,
            "air_pressure_bar": self.air_pressure_bar,
            "exhaust_backpressure_factor": self.exhaust_backpressure_factor,
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
        )


@dataclass
class Combustion:
    thermal_efficiency: float = 0.50  # 0.3 .. 0.7
    burn_duration: float = 50.0  # crank degrees
    ignition_advance: float = 30.0  # degrees BTDC
    afr: float = 13.0  # air-fuel ratio
    chamber_type: str = "Modern Pentroof"
    wiebe_a: float = 5.0
    wiebe_m: float = 2.0

    def to_dict(self) -> dict:
        return {
            "thermal_efficiency": self.thermal_efficiency,
            "burn_duration": self.burn_duration,
            "ignition_advance": self.ignition_advance,
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

    def get_lift(self, angle_deg: float, intake: bool = True) -> float:
        """Approximate valve lift (mm) at a given crank angle using harmonic profile.

        Intake and exhaust lobes are centered independently:
        - Intake center at (lobe_separation - advance) degrees ATDC firing.
        - Exhaust center at (720 - (lobe_separation + advance)) degrees BTDC.

        Angles wrap over 0–720° and the lift shape is a cosine-squared arc.
        """
        duration = self.intake_duration if intake else self.exhaust_duration
        max_lift = self.intake_lift if intake else self.exhaust_lift

        center_intake = self.lobe_separation - self.advance
        center_exhaust = 720.0 - (self.lobe_separation + self.advance)
        center = center_intake if intake else center_exhaust

        span = duration
        start = center - span / 2.0
        start_mod = start % 720.0
        angle = angle_deg % 720.0

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
        )


@dataclass
class Friction:
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
            V_chamber = head.combustion_chamber_vol * 1e-6
        elif head.compression_ratio > 1.0:
            V_chamber = V_swept / (head.compression_ratio - 1.0)
        else:
            return 0.0

        V_total_clearance = V_chamber + V_gasket + V_deck - (head.piston_dome_cc * 1e-6)
        if V_total_clearance <= 0.0:
            return 0.0

        return (V_swept + V_total_clearance) / V_total_clearance


__all__ = [
    "Block",
    "CylinderHead",
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
