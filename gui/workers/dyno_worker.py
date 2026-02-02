from __future__ import annotations

import math
import traceback
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from core.engine_components import Engine
from core.pro_dyno_v2 import ProDynoV2Runner
from core.thermo import CylinderSimulator
from core.units import cc_to_m3


class DynoWorker(QObject):
    progress = Signal(int, str)
    point = Signal(dict)
    finished = Signal(dict)
    cancelled = Signal()
    error = Signal(str)

    def __init__(self, engine_data: dict[str, Any], mode: str, rpm_values: list[int]) -> None:
        super().__init__()
        self._engine_data = engine_data
        self._mode = mode
        self._rpm_values = list(rpm_values)
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    @Slot()
    def run(self) -> None:
        try:
            engine = Engine.from_dict(self._engine_data)
            if self._mode == "v1":
                self._run_v1(engine)
            elif self._mode == "v2":
                self._run_v2(engine)
            else:
                raise ValueError(f"Unknown dyno mode '{self._mode}'")
        except Exception:
            self.error.emit(traceback.format_exc())

    def _emit_progress(self, idx: int, total: int, rpm: int) -> None:
        percent = int(100 * (idx + 1) / max(total, 1))
        msg = f"{self._mode}: RPM {idx + 1}/{total} ({rpm} rpm)"
        self.progress.emit(percent, msg)

    def _run_v1(self, engine: Engine) -> None:
        simulator = CylinderSimulator(engine)
        results: list[dict[str, float]] = []
        total = len(self._rpm_values)
        for idx, rpm in enumerate(self._rpm_values):
            if self._cancel:
                self.cancelled.emit()
                return
            cycle = simulator.run_cycle(float(rpm))
            entry: dict[str, float] = {
                "rpm": float(rpm),
                "mean_power_hp": float(cycle["mean_power_hp"]),
                "mean_torque_nm": float(cycle["mean_torque_nm"]),
                "bmep_bar": float(cycle["bmep_bar"]),
                "ve_actual": float(cycle["ve_actual"]),
            }
            for key in (
                "map_est_kpa",
                "overlap_flow_kg",
                "residual_fraction_est",
                "scavenging_index",
                "boost_kpa",
                "pr_comp",
                "pr_turb",
                "wg_duty",
            ):
                if key in cycle:
                    entry[key] = float(cycle[key])
            results.append(entry)
            payload = dict(entry)
            payload["cycle"] = cycle
            self.point.emit(payload)
            self._emit_progress(idx, total, int(rpm))

        self.finished.emit({"mode": self._mode, "results": results})

    def _run_v2(self, engine: Engine) -> None:
        runner = ProDynoV2Runner(engine)
        results: list[dict[str, float]] = []
        total = len(self._rpm_values)
        displacement_m3 = max(cc_to_m3(engine.block.displacement_cc), 1e-9)
        warm_state: dict[str, Any] | None = None
        for idx, rpm in enumerate(self._rpm_values):
            if self._cancel:
                self.cancelled.emit()
                return
            result, warm_state = runner.run_point(int(rpm), warm_state)
            mean_power_hp = float(result["mean_power_hp"])
            mean_torque_nm = float(result["mean_torque_nm"])
            bmep_bar = mean_torque_nm * 4.0 * math.pi / displacement_m3 / 100000.0
            ve_actual = float(result["ve_real"])
            entry = {
                "rpm": float(rpm),
                "mean_power_hp": mean_power_hp,
                "mean_torque_nm": mean_torque_nm,
                "bmep_bar": float(bmep_bar),
                "ve_actual": ve_actual,
            }
            results.append(entry)
            self.point.emit(entry)
            self._emit_progress(idx, total, int(rpm))

        self.finished.emit({"mode": self._mode, "results": results})
