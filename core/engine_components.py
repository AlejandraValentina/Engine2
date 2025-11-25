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
        single_cyl_vol_m3 = math.pi * (bore_m ** 2) * stroke_m / 4.0
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
    combustion_chamber_vol: Optional[float] = None  # cc override
    port_flow_cfm: float = 200.0  # peak flow at max lift @ 28" H2O per valve

    def to_dict(self) -> dict:
        return {
            "compression_ratio": self.compression_ratio,
            "intake_valves": self.intake_valves,
            "exhaust_valves": self.exhaust_valves,
            "combustion_chamber_vol": self.combustion_chamber_vol,
            "port_flow_cfm": self.port_flow_cfm,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CylinderHead":
        return cls(
            compression_ratio=data.get("compression_ratio", 10.5),
            intake_valves=data.get("intake_valves", 2),
            exhaust_valves=data.get("exhaust_valves", 2),
            combustion_chamber_vol=data.get("combustion_chamber_vol"),
            port_flow_cfm=data.get("port_flow_cfm", 200.0),
        )


@dataclass
class Camshaft:
    intake_lift: float = 10.0  # millimeters
    exhaust_lift: float = 10.0  # millimeters
    intake_duration: float = 260.0  # degrees
    exhaust_duration: float = 260.0  # degrees
    lobe_separation: float = 110.0  # degrees
    advance: float = 0.0  # degrees

    def get_lift(self, angle_deg: float, intake: bool = True) -> float:
        """Approximate valve lift (mm) at a given crank angle.

        Uses a simple harmonic profile centered around TDC firing (~360°) with
        intake and exhaust centers separated by the lobe separation angle. The
        optional advance shifts both centers equally. Angles wrap over 0–720°.
        """
        duration = self.intake_duration if intake else self.exhaust_duration
        max_lift = self.intake_lift if intake else self.exhaust_lift

        center_intake = 360.0 - self.lobe_separation / 2.0 + self.advance
        center_exhaust = 360.0 + self.lobe_separation / 2.0 + self.advance
        center = center_intake if intake else center_exhaust

        start = center - duration / 2.0
        start_mod = start % 720.0
        angle = angle_deg % 720.0

        # Normalize active interval handling wrap-around
        if duration >= 720.0:
            phase = 0.5
        else:
            end_mod = (start_mod + duration) % 720.0
            if start_mod <= end_mod:
                active = start_mod <= angle <= end_mod
                rel = angle - start_mod if active else -1.0
            else:
                active = angle >= start_mod or angle <= end_mod
                rel = (angle - start_mod) % 720.0 if active else -1.0
            if not active:
                return 0.0
            phase = rel / duration

        return max_lift * 0.5 * (1.0 - math.cos(math.pi * phase))

    def to_dict(self) -> dict:
        return {
            "intake_lift": self.intake_lift,
            "exhaust_lift": self.exhaust_lift,
            "intake_duration": self.intake_duration,
            "exhaust_duration": self.exhaust_duration,
            "lobe_separation": self.lobe_separation,
            "advance": self.advance,
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
        )


@dataclass
class IntakeSystem:
    runner_length: float = 300.0  # millimeters
    runner_diameter: float = 45.0  # millimeters
    plenum_volume: float = 3.0  # liters
    throttle_body_dia: float = 70.0  # millimeters
    throttle_cfm: float = 500.0  # carb/throttle flow rating

    def to_dict(self) -> dict:
        return {
            "runner_length": self.runner_length,
            "runner_diameter": self.runner_diameter,
            "plenum_volume": self.plenum_volume,
            "throttle_body_dia": self.throttle_body_dia,
            "throttle_cfm": self.throttle_cfm,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IntakeSystem":
        return cls(
            runner_length=data.get("runner_length", 300.0),
            runner_diameter=data.get("runner_diameter", 45.0),
            plenum_volume=data.get("plenum_volume", 3.0),
            throttle_body_dia=data.get("throttle_body_dia", 70.0),
            throttle_cfm=data.get("throttle_cfm", 500.0),
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

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "boost_pressure_bar": self.boost_pressure_bar,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Supercharger":
        return cls(
            type=data.get("type", "NA"),
            boost_pressure_bar=data.get("boost_pressure_bar", 0.0),
        )


@dataclass
class Engine:
    block: Block = field(default_factory=Block)
    head: CylinderHead = field(default_factory=CylinderHead)
    camshaft: Camshaft = field(default_factory=Camshaft)
    intake: IntakeSystem = field(default_factory=IntakeSystem)
    exhaust: ExhaustSystem = field(default_factory=ExhaustSystem)
    supercharger: Supercharger = field(default_factory=Supercharger)

    def to_dict(self) -> dict:
        return {
            "block": self.block.to_dict(),
            "head": self.head.to_dict(),
            "camshaft": self.camshaft.to_dict(),
            "intake": self.intake.to_dict(),
            "exhaust": self.exhaust.to_dict(),
            "supercharger": self.supercharger.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Engine":
        cam_data = data.get("camshaft") or data.get("cam") or {}
        return cls(
            block=Block.from_dict(data.get("block", {})),
            head=CylinderHead.from_dict(data.get("head", {})),
            camshaft=Camshaft.from_dict(cam_data),
            intake=IntakeSystem.from_dict(data.get("intake", {})),
            exhaust=ExhaustSystem.from_dict(data.get("exhaust", {})),
            supercharger=Supercharger.from_dict(data.get("supercharger", {})),
        )

    def save_to_file(self, filename: str) -> None:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, filename: str) -> "Engine":
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


__all__ = [
    "Block",
    "CylinderHead",
    "Camshaft",
    "IntakeSystem",
    "ExhaustSystem",
    "Supercharger",
    "Engine",
]
