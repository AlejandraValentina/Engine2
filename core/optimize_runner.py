from __future__ import annotations

import json
import random
from dataclasses import dataclass

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@dataclass
class OptimizeReport:
    params_initial: dict
    params_best: dict
    error_initial: float
    error_best: float
    evals_used: int
    seed: int
    status: str

    def to_dict(self) -> dict:
        return {
            "params_initial": self.params_initial,
            "params_best": self.params_best,
            "error_initial": float(self.error_initial),
            "error_best": float(self.error_best),
            "evals_used": int(self.evals_used),
            "seed": int(self.seed),
            "status": self.status,
        }


def _relative_error(pred: float, target: float, eps: float = 1e-9) -> float:
    denom = max(abs(target), eps)
    return (pred - target) / denom


def _evaluate(engine: Engine, target_points: list[dict]) -> float:
    sim = CylinderSimulator(engine)
    total = 0.0
    count = 0
    for tgt in target_points:
        rpm = float(tgt["rpm"])
        cycle = sim.run_cycle(rpm)
        for key in ("power_hp", "torque_nm", "bmep_bar", "ve_actual"):
            if key in tgt:
                pred_key = "mean_power_hp" if key == "power_hp" else "mean_torque_nm" if key == "torque_nm" else key
                pred = float(cycle[pred_key])
                err = _relative_error(pred, float(tgt[key]))
                total += err * err
                count += 1
    if count == 0:
        raise ValueError("target points must include at least one of power_hp/torque_nm/bmep_bar/ve_actual")
    return total / count


def _grid(low: float, high: float, count: int) -> list[float]:
    if count <= 1:
        return [(low + high) * 0.5]
    step = (high - low) / (count - 1)
    return [low + i * step for i in range(count)]


def optimize_runner_length(
    engine: Engine,
    target_points: list[dict],
    bounds_m: tuple[float, float],
    seed: int,
    max_evals: int,
    param: str = "intake.runner_length",
) -> OptimizeReport:
    if max_evals < 1:
        raise ValueError("max_evals must be >= 1")
    if param != "intake.runner_length":
        raise ValueError("Only intake.runner_length is supported for optimize")

    low_m, high_m = bounds_m
    if low_m <= 0.0 or high_m <= 0.0 or high_m <= low_m:
        raise ValueError("bounds must be positive and low < high")

    base_length_m = float(engine.intake.runner_length) / 1000.0
    params_initial = {param: base_length_m}

    base_engine = Engine.from_dict(engine.to_dict())
    error_initial = _evaluate(base_engine, target_points)
    best_error = error_initial
    best_params = dict(params_initial)
    evals_used = 1

    remaining = max_evals - 1
    if remaining > 0:
        grid_count = min(remaining, 12)
        candidates = _grid(low_m, high_m, grid_count)
        rng = random.Random(int(seed))
        rng.shuffle(candidates)
        for value_m in candidates:
            if evals_used >= max_evals:
                break
            if abs(value_m - base_length_m) <= 1e-9:
                continue
            trial_engine = Engine.from_dict(engine.to_dict())
            trial_engine.intake.runner_length = value_m * 1000.0
            err = _evaluate(trial_engine, target_points)
            evals_used += 1
            if err < best_error:
                best_error = err
                best_params = {param: float(value_m)}

    status = "complete" if evals_used < max_evals else "max_evals"
    return OptimizeReport(
        params_initial=params_initial,
        params_best=best_params,
        error_initial=error_initial,
        error_best=best_error,
        evals_used=evals_used,
        seed=int(seed),
        status=status,
    )


def load_target_points(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.loads(handle.read())
    points = payload.get("points", [])
    if not isinstance(points, list):
        raise ValueError("target points must be a list")
    return points
