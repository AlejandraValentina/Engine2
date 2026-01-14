"""Compatibility layer for legacy project structures.

The canonical engine schema lives in ``core.engine_components``. This module
re-exports key dataclasses and provides a thin ``EngineProject`` wrapper so
older tooling can bundle an engine with optional pipe/junction metadata without
duplicating definitions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from core.engine_components import Engine, Pipe, SimulationSettings
from core.advanced.junctions import JunctionLegConfig
from core.junctions import Junction


@dataclass
class CylinderGeometry:
    """Geometric properties of a cylinder (legacy helper)."""

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
class EngineProject:
    """Aggregate an ``Engine`` with optional pipe/junction metadata."""

    name: str = "Untitled Engine"
    engine: Engine = field(default_factory=Engine)
    pipes: Dict[str, Pipe] = field(default_factory=dict)
    junctions: Dict[str, Junction] = field(default_factory=dict)
    junction_legs: Dict[str, Dict[str, JunctionLegConfig]] = field(default_factory=dict)
    banks: Dict[str, List[CylinderNode]] = field(default_factory=dict)  # legacy

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "engine": self.engine.to_dict(),
            "pipes": {pipe_id: pipe.to_dict() for pipe_id, pipe in self.pipes.items()},
            "junctions": {
                jid: {
                    "volume": j.volume,
                    "pressure": getattr(j, "pressure", 101325.0),
                    "temperature": getattr(j, "temperature", 300.0),
                    "legs": {
                        leg_id: leg.to_dict()
                        for leg_id, leg in self.junction_legs.get(jid, {}).items()
                    },
                }
                for jid, j in self.junctions.items()
            },
            "banks": {  # legacy passthrough
                bank_name: [cyl.to_dict() for cyl in cylinders]
                for bank_name, cylinders in self.banks.items()
            },
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "EngineProject":
        engine_payload = data.get("engine", data)
        engine = Engine.from_dict(engine_payload)

        pipes_data = data.get("pipes", {})
        pipes: Dict[str, Pipe] = {
            pipe_id: Pipe.from_dict(pipe_dict) for pipe_id, pipe_dict in pipes_data.items()
        }

        junctions_data = data.get("junctions", {})
        junctions: Dict[str, Junction] = {}
        junction_legs: Dict[str, Dict[str, JunctionLegConfig]] = {}
        for jid, junc_dict in junctions_data.items():
            vol = junc_dict.get("volume", 0.001)
            p = junc_dict.get("pressure", 101325.0)
            T = junc_dict.get("temperature", 300.0)
            junctions[jid] = Junction(vol, p, T)
            legs_data = junc_dict.get("legs", {})
            if isinstance(legs_data, dict) and legs_data:
                junction_legs[jid] = {
                    leg_id: JunctionLegConfig.from_dict(leg_dict)
                    for leg_id, leg_dict in legs_data.items()
                }

        banks_data = data.get("banks", {})
        banks: Dict[str, List[CylinderNode]] = {
            bank_name: [CylinderNode.from_dict(cyl) for cyl in cylinders]
            for bank_name, cylinders in banks_data.items()
        }

        name = data.get("name") or engine_payload.get("model_name", "Untitled Engine")
        return cls(
            name=name,
            engine=engine,
            pipes=pipes,
            junctions=junctions,
            junction_legs=junction_legs,
            banks=banks,
        )


__all__ = [
    "SimulationSettings",
    "CylinderGeometry",
    "CylinderNode",
    "Pipe",
    "Junction",
    "EngineProject",
    "Engine",
]
