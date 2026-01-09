from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from core.advanced.coupling import ValveTiming
from core.advanced.orchestrator import Orchestrator, OrchestratorConfig
from core.engine_components import Engine


@dataclass
class ProDynoV2Result:
    rpm: int
    mean_power_hp: float
    mean_torque_nm: float
    ve_real: float
    residual_frac: float


class ProDynoV2Runner:
    """Run the v2 Advanced Core for Pro Dyno sweeps."""

    def __init__(self, engine: Engine, settings: Optional[dict[str, Any]] = None) -> None:
        self.engine = engine
        self.settings = settings or {}
        self._last_state: Optional[dict[str, Any]] = None

    def _build_orchestrator(self, warm_start: bool) -> Orchestrator:
        max_cycles = int(self.settings.get("max_cycles", 4))
        if warm_start:
            max_cycles = max(2, min(max_cycles, 3))
        cp_value = self.settings.get("cp") if "cp" in self.settings else None
        cfg = OrchestratorConfig(
            gamma=float(self.settings.get("gamma", 1.35)),
            gas_constant=float(self.settings.get("gas_constant", 287.0)),
            cp=float(cp_value) if cp_value is not None else None,
            cfl=float(self.settings.get("cfl", 0.5)),
            dt_max=float(self.settings.get("dt_max", 5e-5)),
            max_cycles=max_cycles,
        )
        return Orchestrator(cfg)

    def _default_pipe(self) -> tuple[int, float, float]:
        cells = int(self.settings.get("pipe_cells", 40))
        length_m = float(self.settings.get("pipe_length_m", 0.6))
        diameter_m = float(self.settings.get("pipe_diameter_m", 0.04))
        return cells, length_m, diameter_m

    def _default_valve(self) -> ValveTiming:
        cam = self.engine.camshaft
        head = self.engine.head
        seat_mm = head.exhaust_valve_seat_diameter_mm or head.exhaust_valve_diameter_mm
        seat_m = float(seat_mm) * 1e-3
        lift_m = float(cam.exhaust_lift) * 1e-3
        return ValveTiming(
            open_start_deg=360.0,
            open_end_deg=540.0,
            max_lift_m=lift_m,
            seat_diameter_m=seat_m,
            cd=float(self.settings.get("valve_cd", 0.9)),
        )

    def run_point(self, rpm: int, warm_start_state: Optional[dict[str, Any]] = None) -> tuple[dict[str, Any], dict[str, Any]]:
        warm_start = warm_start_state is not None
        orchestrator = self._build_orchestrator(warm_start)
        cells, length_m, diameter_m = self._default_pipe()
        block = self.engine.block
        bore_m = float(block.bore) * 1e-3
        stroke_m = float(block.stroke) * 1e-3
        conrod_m = float(block.conrod_length) * 1e-3
        area = math.pi * (bore_m * 0.5) ** 2
        clearance_m3 = area * stroke_m / max(self.engine.head.compression_ratio - 1.0, 1e-6)

        valve = self._default_valve()
        result = orchestrator.run(
            rpm=float(rpm),
            pipe_cells=cells,
            pipe_length_m=length_m,
            pipe_diameter_m=diameter_m,
            bore_m=bore_m,
            stroke_m=stroke_m,
            conrod_m=conrod_m,
            clearance_m3=clearance_m3,
            valve=valve,
        )

        indicated_work = result["indicated_work"][-1] if result["indicated_work"] else 0.0
        mean_torque_nm = max(indicated_work / (2.0 * math.pi), 0.0)
        omega = float(rpm) * 2.0 * math.pi / 60.0
        mean_power_hp = max(mean_torque_nm * omega / 745.7, 0.0)

        ve_real = max(result["ve"], default=0.0)
        trapped = result["trapped_mass"][-1] if result["trapped_mass"] else 0.0
        residual = 1.0 - min(trapped / max(result["trapped_mass"][0], 1e-9), 1.0) if result["trapped_mass"] else 0.0

        out = {
            "mean_power_hp": mean_power_hp,
            "mean_torque_nm": mean_torque_nm,
            "ve_real": ve_real,
            "residual_frac": residual,
        }
        state_out = {"last_result": result}
        return out, state_out

    def run_sweep(self, rpm_values: list[int]) -> dict[str, list[float]]:
        results = {
            "rpm": [],
            "mean_power_hp": [],
            "mean_torque_nm": [],
            "ve_real": [],
            "residual_frac": [],
        }
        warm_state: Optional[dict[str, Any]] = None
        for rpm in rpm_values:
            result, warm_state = self.run_point(int(rpm), warm_state)
            results["rpm"].append(int(rpm))
            results["mean_power_hp"].append(float(result["mean_power_hp"]))
            results["mean_torque_nm"].append(float(result["mean_torque_nm"]))
            results["ve_real"].append(float(result["ve_real"]))
            results["residual_frac"].append(float(result["residual_frac"]))
        self._last_state = warm_state
        return results
