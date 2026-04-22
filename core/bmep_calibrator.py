from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@dataclass
class BmepCalibrationResult:
    target_rpm: float
    target_bmep_bar: float
    ca50_grid: list[float]
    duration_grid: list[float]
    evaluations: list[dict]
    best: dict | None
    status: str
    used_no_knock_filter: bool

    def to_dict(self) -> dict:
        return {
            "target": {
                "rpm": float(self.target_rpm),
                "bmep_bar": float(self.target_bmep_bar),
            },
            "ranges": {
                "ca50_deg_atdc": [float(v) for v in self.ca50_grid],
                "burn_duration_deg": [float(v) for v in self.duration_grid],
            },
            "evaluations": self.evaluations,
            "best": self.best,
            "status": self.status,
            "used_no_knock_filter": bool(self.used_no_knock_filter),
        }


def _grid(values: Iterable[float]) -> list[float]:
    return [float(v) for v in values]


def _apply_wiebe(engine: Engine, ca50_deg_atdc: float, burn_duration_deg: float, wiebe_a: float | None, wiebe_m: float | None) -> None:
    base = dict(getattr(engine.combustion, "wiebe", {}) or {})
    base["enabled"] = True
    base["ca50_deg_atdc"] = float(ca50_deg_atdc)
    base["burn_duration_deg"] = float(burn_duration_deg)
    if wiebe_a is not None:
        base["a"] = float(wiebe_a)
    if wiebe_m is not None:
        base["m"] = float(wiebe_m)
    engine.combustion.wiebe = base


def calibrate_bmep(
    engine: Engine,
    rpm: float,
    target_bmep_bar: float,
    ca50_grid: Iterable[float],
    duration_grid: Iterable[float],
    *,
    wiebe_a: float | None = None,
    wiebe_m: float | None = None,
    require_no_knock: bool = True,
) -> BmepCalibrationResult:
    ca50_values = _grid(ca50_grid)
    duration_values = _grid(duration_grid)
    if not ca50_values:
        raise ValueError("ca50 grid must not be empty")
    if not duration_values:
        raise ValueError("duration grid must not be empty")

    evaluations: list[dict] = []
    for ca50 in ca50_values:
        for duration in duration_values:
            trial = Engine.from_dict(engine.to_dict())
            _apply_wiebe(trial, ca50, duration, wiebe_a, wiebe_m)
            cycle = CylinderSimulator(trial).run_cycle(rpm)
            entry = {
                "ca50_deg_atdc": float(ca50),
                "burn_duration_deg": float(duration),
                "bmep_bar": float(cycle["bmep_bar"]),
                "mean_power_hp": float(cycle["mean_power_hp"]),
                "mean_torque_nm": float(cycle["mean_torque_nm"]),
            }
            if "knock_warning" in cycle:
                entry["knock_warning"] = bool(cycle["knock_warning"])
            evaluations.append(entry)

    target = float(target_bmep_bar)
    valid = [e for e in evaluations if float(e["bmep_bar"]) >= target]
    used_no_knock_filter = False
    if require_no_knock and valid:
        no_knock = [e for e in valid if not bool(e.get("knock_warning", False))]
        if no_knock:
            valid = no_knock
            used_no_knock_filter = True

    best = None
    status = "success"
    if valid:
        best = min(
            valid,
            key=lambda e: (
                float(e["bmep_bar"]) - target,
                -float(e["burn_duration_deg"]),
                -float(e["ca50_deg_atdc"]),
            ),
        )
        if require_no_knock and not used_no_knock_filter and any(
            bool(e.get("knock_warning", False)) for e in valid
        ):
            status = "target_met_with_knock"
    else:
        no_knock = [e for e in evaluations if not bool(e.get("knock_warning", False))]
        candidates = no_knock if no_knock else evaluations
        if candidates:
            best = max(
                candidates,
                key=lambda e: (
                    float(e["bmep_bar"]),
                    float(e["burn_duration_deg"]),
                    float(e["ca50_deg_atdc"]),
                ),
            )
        status = "target_not_met"
        if require_no_knock and not no_knock:
            status = "no_nonknock_candidates"

    return BmepCalibrationResult(
        target_rpm=float(rpm),
        target_bmep_bar=float(target_bmep_bar),
        ca50_grid=ca50_values,
        duration_grid=duration_values,
        evaluations=evaluations,
        best=best,
        status=status,
        used_no_knock_filter=used_no_knock_filter,
    )
