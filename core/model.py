"""Data models for PyWaveDyn engine configuration."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SimulationSettings:
    """Simulation-level settings including RPM range and acoustic resolution."""

    rpm_start: float = 1000.0
    rpm_end: float = 8000.0
    acoustic_resolution_hz: float = 44100.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "rpm_start": self.rpm_start,
            "rpm_end": self.rpm_end,
            "acoustic_resolution_hz": self.acoustic_resolution_hz,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SimulationSettings":
        return cls(
            rpm_start=data.get("rpm_start", 1000.0),
            rpm_end=data.get("rpm_end", 8000.0),
            acoustic_resolution_hz=data.get("acoustic_resolution_hz", 44100.0),
        )


@dataclass
class CylinderGeometry:
    """Geometric properties of a cylinder."""

    bore: float = 86.0
    stroke: float = 86.0
    conrod_length: float = 143.0
    compression_ratio: float = 10.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "bore": self.bore,
            "stroke": self.stroke,
            "conrod_length": self.conrod_length,
            "compression_ratio": self.compression_ratio,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CylinderGeometry":
        return cls(
            bore=data.get("bore", 86.0),
            stroke=data.get("stroke", 86.0),
            conrod_length=data.get("conrod_length", 143.0),
            compression_ratio=data.get("compression_ratio", 10.0),
        )


@dataclass
class CylinderNode:
    """A cylinder instance within a bank, with geometry and firing angle."""

    geometry: CylinderGeometry = field(default_factory=CylinderGeometry)
    firing_angle: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "geometry": self.geometry.to_dict(),
            "firing_angle": self.firing_angle,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CylinderNode":
        geometry_data = data.get("geometry", {})
        return cls(
            geometry=CylinderGeometry.from_dict(geometry_data),
            firing_angle=data.get("firing_angle", 0.0),
        )


@dataclass
class Pipe:
    """Representation of a duct segment used in intake or exhaust systems."""

    length: float = 500.0
    diameter_inlet: float = 45.0
    diameter_outlet: float = 45.0
    wall_temperature: float = 600.0
    friction_coeff: float = 0.02

    def to_dict(self) -> Dict[str, float]:
        return {
            "length": self.length,
            "diameter_inlet": self.diameter_inlet,
            "diameter_outlet": self.diameter_outlet,
            "wall_temperature": self.wall_temperature,
            "friction_coeff": self.friction_coeff,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Pipe":
        return cls(
            length=data.get("length", 500.0),
            diameter_inlet=data.get("diameter_inlet", 45.0),
            diameter_outlet=data.get("diameter_outlet", 45.0),
            wall_temperature=data.get("wall_temperature", 600.0),
            friction_coeff=data.get("friction_coeff", 0.02),
        )


@dataclass
class Junction:
    """A junction connecting pipes, optionally representing a plenum volume."""

    volume: float = 0.001
    junction_type: str = "merge"

    def to_dict(self) -> Dict:
        return {
            "volume": self.volume,
            "junction_type": self.junction_type,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Junction":
        return cls(
            volume=data.get("volume", 0.001),
            junction_type=data.get("junction_type", "merge"),
        )


@dataclass
class EngineProject:
    """Root container for an engine configuration, including topology and network."""

    name: str = "Untitled Engine"
    simulation_settings: SimulationSettings = field(default_factory=SimulationSettings)
    banks: Dict[str, List[CylinderNode]] = field(default_factory=dict)
    pipes: Dict[str, Pipe] = field(default_factory=dict)
    junctions: Dict[str, Junction] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "simulation_settings": self.simulation_settings.to_dict(),
            "banks": {
                bank_name: [cyl.to_dict() for cyl in cylinders]
                for bank_name, cylinders in self.banks.items()
            },
            "pipes": {pipe_id: pipe.to_dict() for pipe_id, pipe in self.pipes.items()},
            "junctions": {
                junction_id: junction.to_dict()
                for junction_id, junction in self.junctions.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "EngineProject":
        settings_data = data.get("simulation_settings", {})
        banks_data = data.get("banks", {})
        pipes_data = data.get("pipes", {})
        junctions_data = data.get("junctions", {})

        banks: Dict[str, List[CylinderNode]] = {}
        for bank_name, cylinders in banks_data.items():
            banks[bank_name] = [CylinderNode.from_dict(cyl) for cyl in cylinders]

        pipes: Dict[str, Pipe] = {
            pipe_id: Pipe.from_dict(pipe_dict) for pipe_id, pipe_dict in pipes_data.items()
        }

        junctions: Dict[str, Junction] = {
            junction_id: Junction.from_dict(junc_dict)
            for junction_id, junc_dict in junctions_data.items()
        }

        return cls(
            name=data.get("name", "Untitled Engine"),
            simulation_settings=SimulationSettings.from_dict(settings_data),
            banks=banks,
            pipes=pipes,
            junctions=junctions,
        )


__all__ = [
    "SimulationSettings",
    "CylinderGeometry",
    "CylinderNode",
    "Pipe",
    "Junction",
    "EngineProject",
]
