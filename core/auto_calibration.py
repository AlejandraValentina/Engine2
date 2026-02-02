from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Iterable
import random

from core.engine_components import Engine
from core.thermo import CylinderSimulator


_ALLOWED_PARAMS = {"ve_scale", "friction_scale", "burn_scale"}


@dataclass
class CalibrationReport:
    params_initial: dict
    params_final: dict
    error_initial: float
    error_final: float
    evals_used: int
    status: str

    def to_dict(self) -> dict:
        return {
            "params_initial": self.params_initial,
            "params_final": self.params_final,
            "error_initial": float(self.error_initial),
            "error_final": float(self.error_final),
            "evals_used": int(self.evals_used),
            "status": self.status,
        }


def _apply_scales(engine: Engine, params: dict) -> None:
    if "ve_scale" in params:
        scale = float(params["ve_scale"])
        engine.head.port_flow_efficiency = max(0.1, min(engine.head.port_flow_efficiency * scale, 1.5))
    if "friction_scale" in params:
        scale = float(params["friction_scale"])
        engine.friction.global_scaling_factor = max(engine.friction.global_scaling_factor * scale, 0.1)
    if "burn_scale" in params:
        scale = float(params["burn_scale"])
        engine.combustion.thermal_efficiency = max(0.0, min(engine.combustion.thermal_efficiency * scale, 1.0))


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


def _grid_values() -> list[float]:
    return [0.8, 1.0, 1.2]


def _param_bounds() -> tuple[float, float]:
    grid = _grid_values()
    return min(grid), max(grid)


def _sorted_params(params: Iterable[str]) -> list[str]:
    return [p.strip() for p in params if p.strip()]


def calibrate_engine(
    engine: Engine,
    target_points: list[dict],
    params: Iterable[str],
    max_evals: int,
) -> CalibrationReport:
    if max_evals < 1:
        raise ValueError("max_evals must be >= 1")

    params = _sorted_params(params)
    for p in params:
        if p not in _ALLOWED_PARAMS:
            raise ValueError(f"Unknown calibration param '{p}'")

    params_initial = {p: 1.0 for p in params}

    base_engine = Engine.from_dict(engine.to_dict())
    _apply_scales(base_engine, params_initial)
    error_initial = _evaluate(base_engine, target_points)
    best_error = error_initial
    best_params = dict(params_initial)
    evals_used = 1

    grid = _grid_values()
    if params:
        for values in itertools.product(grid, repeat=len(params)):
            if evals_used >= max_evals:
                break
            candidate = dict(zip(params, values))
            if candidate == params_initial:
                continue
            trial_engine = Engine.from_dict(engine.to_dict())
            _apply_scales(trial_engine, candidate)
            err = _evaluate(trial_engine, target_points)
            evals_used += 1
            if err < best_error:
                best_error = err
                best_params = dict(candidate)

    status = "complete" if evals_used < max_evals else "max_evals"
    return CalibrationReport(
        params_initial=params_initial,
        params_final=best_params,
        error_initial=error_initial,
        error_final=best_error,
        evals_used=evals_used,
        status=status,
    )


def calibrate_engine_diagnostics(
    engine: Engine,
    target_points: list[dict],
    params: Iterable[str],
    max_evals: int,
    *,
    multi_start: int = 1,
    top_k: int = 5,
    seed: int = 0,
    eps_obj: float = 1e-3,
    eps_params: float = 0.05,
) -> dict:
    if max_evals < 1:
        raise ValueError("max_evals must be >= 1")
    if multi_start < 1:
        raise ValueError("multi_start must be >= 1")
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    params = _sorted_params(params)
    for p in params:
        if p not in _ALLOWED_PARAMS:
            raise ValueError(f"Unknown calibration param '{p}'")

    params_initial = {p: 1.0 for p in params}
    bounds = _param_bounds()
    rng = random.Random(seed)

    candidates: list[dict] = []
    candidates.append(params_initial)

    grid = _grid_values()
    if params:
        for values in itertools.product(grid, repeat=len(params)):
            candidates.append(dict(zip(params, values)))

    for _ in range(multi_start):
        candidates.append({p: rng.uniform(bounds[0], bounds[1]) for p in params})

    seen = set()
    unique_candidates: list[dict] = []
    for candidate in candidates:
        key = tuple(round(float(candidate[p]), 6) for p in params)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)

    results: list[dict] = []
    evals_used = 0
    for candidate in unique_candidates:
        if evals_used >= max_evals:
            break
        trial_engine = Engine.from_dict(engine.to_dict())
        _apply_scales(trial_engine, candidate)
        err = _evaluate(trial_engine, target_points)
        results.append({"params": dict(candidate), "objective": float(err)})
        evals_used += 1

    if not results:
        raise RuntimeError("calibration diagnostics produced no evaluations")

    results_sorted = sorted(results, key=lambda item: item["objective"])
    best = results_sorted[0]
    top_k = min(top_k, len(results_sorted))
    top_entries = results_sorted[:top_k]

    near = [r for r in results_sorted if r["objective"] <= best["objective"] + eps_obj]
    param_spread = {p: 0.0 for p in params}
    for p in params:
        values = [float(r["params"].get(p, 1.0)) for r in near]
        if values:
            param_spread[p] = max(values) - min(values)
    obj_spread = max(r["objective"] for r in near) - min(r["objective"] for r in near)

    unique = True
    reason = "unique"
    for r in near:
        if r is best:
            continue
        max_diff = 0.0
        for p in params:
            max_diff = max(max_diff, abs(float(r["params"].get(p, 1.0)) - float(best["params"].get(p, 1.0))))
        if max_diff > eps_params:
            unique = False
            reason = "non_identifiable"
            break

    status = "complete" if evals_used < max_evals else "max_evals"
    return {
        "metadata": {
            "seed": int(seed),
            "multi_start": int(multi_start),
            "eps_obj": float(eps_obj),
            "eps_params": float(eps_params),
            "bounds": {"min": float(bounds[0]), "max": float(bounds[1])},
            "top_k": int(top_k),
        },
        "best_solution": best,
        "top_k": top_entries,
        "uniqueness": {
            "unique": bool(unique),
            "reason": reason,
            "param_spread": param_spread,
            "obj_spread": float(obj_spread),
        },
        "evals_used": int(evals_used),
        "status": status,
    }
