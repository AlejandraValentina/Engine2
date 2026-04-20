from __future__ import annotations

import json
import itertools
import random
from dataclasses import dataclass
from pathlib import Path

from core.auto_calibration import _apply_scales, _initial_param_value
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


@dataclass
class GuidedOptimizeReport:
    optimization_problem: dict
    baseline: dict
    best_candidate: dict
    candidates: list[dict]
    warnings: list[str]
    evals_used: int
    seed: int
    status: str

    def to_dict(self) -> dict:
        return {
            "optimization_problem": self.optimization_problem,
            "baseline": self.baseline,
            "best_candidate": self.best_candidate,
            "candidates": self.candidates,
            "warnings": self.warnings,
            "evals_used": int(self.evals_used),
            "seed": int(self.seed),
            "status": self.status,
        }


_GUIDED_PARAM_DEFAULTS = {
    "intake.runner_length": {"kind": "bounded_linear", "default_span": 0.2},
    "ve_scale": {"kind": "grid", "values": [0.9, 1.0, 1.1]},
    "friction_scale": {"kind": "grid", "values": [0.9, 1.0, 1.1]},
    "burn_scale": {"kind": "grid", "values": [0.9, 1.0, 1.1]},
    "adaptive_duration_scale": {"kind": "relative", "values": [0.9, 1.0, 1.1]},
    "adaptive_ca50_offset_deg": {"kind": "offset", "values": [-2.0, 0.0, 2.0]},
    "turbo_target_boost_scale": {"kind": "grid", "values": [0.9, 1.0, 1.1]},
    "turbo_spool_rpm_offset": {"kind": "grid", "values": [-500.0, 0.0, 500.0]},
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


def _evaluate_dataset_metrics(engine: Engine, target_points: list[dict]) -> dict:
    sim = CylinderSimulator(engine)
    total = 0.0
    count = 0
    per_signal: dict[str, list[float]] = {}
    for tgt in target_points:
        rpm = float(tgt["rpm"])
        cycle = sim.run_cycle(rpm)
        for key in ("power_hp", "torque_nm", "bmep_bar", "ve_actual", "boost_kpa", "map_kpa"):
            if key not in tgt:
                continue
            pred_key = "mean_power_hp" if key == "power_hp" else "mean_torque_nm" if key == "torque_nm" else "map_est_kpa" if key == "map_kpa" else key
            pred = float(cycle[pred_key])
            err = _relative_error(pred, float(tgt[key]))
            total += err * err
            count += 1
            per_signal.setdefault(key, []).append(abs(err))
    if count == 0:
        raise ValueError("target points must include at least one supported signal")
    signal_mape = {
        signal: float(sum(values) / max(len(values), 1))
        for signal, values in sorted(per_signal.items())
    }
    return {
        "objective_score": float(total / count),
        "signal_mape": signal_mape,
        "signals_scored": sorted(signal_mape.keys()),
    }


def _dyno_band_metrics(engine: Engine, rpm_values: list[float]) -> dict:
    sim = CylinderSimulator(engine)
    rows = []
    for rpm in rpm_values:
        cycle = sim.run_cycle(float(rpm))
        row = {
            "rpm": float(rpm),
            "power_hp": float(cycle["mean_power_hp"]),
            "torque_nm": float(cycle["mean_torque_nm"]),
        }
        if "boost_kpa" in cycle:
            row["boost_kpa"] = float(cycle["boost_kpa"])
        rows.append(row)
    peak_power_hp = max(row["power_hp"] for row in rows)
    mean_torque_nm = sum(row["torque_nm"] for row in rows) / max(len(rows), 1)
    payload = {
        "rpm_grid": [float(rpm) for rpm in rpm_values],
        "peak_power_hp": float(peak_power_hp),
        "mean_torque_nm": float(mean_torque_nm),
    }
    boosts = [row["boost_kpa"] for row in rows if "boost_kpa" in row]
    if boosts:
        payload["mean_boost_kpa"] = float(sum(boosts) / len(boosts))
        payload["peak_boost_kpa"] = float(max(boosts))
    return payload


def _grid(low: float, high: float, count: int) -> list[float]:
    if count <= 1:
        return [(low + high) * 0.5]
    step = (high - low) / (count - 1)
    return [low + i * step for i in range(count)]


def _apply_guided_param(engine: Engine, param: str, value: float) -> None:
    if param == "intake.runner_length":
        engine.intake.runner_length = float(value) * 1000.0
        return
    _apply_scales(engine, {param: float(value)})


def _initial_guided_param_value(engine: Engine, param: str) -> float:
    if param == "intake.runner_length":
        return float(engine.intake.runner_length) / 1000.0
    return float(_initial_param_value(engine, param))


def _param_candidate_values(engine: Engine, param: str, bounds: tuple[float, float] | None) -> list[float]:
    if param not in _GUIDED_PARAM_DEFAULTS:
        raise ValueError(f"Unsupported guided optimize param '{param}'")
    cfg = _GUIDED_PARAM_DEFAULTS[param]
    kind = str(cfg["kind"])
    if bounds is not None:
        low, high = bounds
        if low >= high:
            raise ValueError(f"Invalid bounds for '{param}': low must be < high")
        return [float(v) for v in _grid(float(low), float(high), 5)]
    base = _initial_guided_param_value(engine, param)
    if kind == "bounded_linear":
        span = float(cfg.get("default_span", 0.2))
        low = max(base * (1.0 - span), 0.01)
        high = max(base * (1.0 + span), low + 1e-6)
        return [float(v) for v in _grid(low, high, 5)]
    if kind == "grid":
        return [float(v) for v in cfg["values"]]
    if kind == "relative":
        return [max(base * float(v), 0.1) for v in cfg["values"]]
    if kind == "offset":
        return [base + float(v) for v in cfg["values"]]
    raise ValueError(f"Unsupported guided optimize kind '{kind}'")


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


def optimize_guided(
    engine: Engine,
    *,
    objective: str,
    params: list[str],
    seed: int,
    max_evals: int,
    target_points: list[dict] | None = None,
    rpm_grid: list[float] | None = None,
    param_bounds: dict[str, tuple[float, float]] | None = None,
    constraints: dict | None = None,
) -> GuidedOptimizeReport:
    if max_evals < 1:
        raise ValueError("max_evals must be >= 1")
    if not params:
        raise ValueError("guided optimize requires at least one param")
    if len(params) > 2:
        raise ValueError("guided optimize supports at most 2 params in this iteration")
    params = [str(p).strip() for p in params if str(p).strip()]
    for param in params:
        if param not in _GUIDED_PARAM_DEFAULTS:
            raise ValueError(f"Unsupported guided optimize param '{param}'")
    objective = str(objective).strip().lower()
    constraints = dict(constraints or {})
    param_bounds = dict(param_bounds or {})

    if objective == "dataset_error":
        if not target_points:
            raise ValueError("dataset_error objective requires target_points")
    elif objective in {"peak_power", "mean_torque_band", "boost_target_tracking"}:
        if not rpm_grid:
            raise ValueError(f"{objective} objective requires rpm_grid")
    else:
        raise ValueError("objective must be one of ['dataset_error', 'peak_power', 'mean_torque_band', 'boost_target_tracking']")

    def evaluate_candidate(candidate_params: dict[str, float]) -> dict:
        trial_engine = Engine.from_dict(engine.to_dict())
        for key, value in candidate_params.items():
            _apply_guided_param(trial_engine, key, float(value))

        objective_metrics: dict
        if objective == "dataset_error":
            objective_metrics = _evaluate_dataset_metrics(trial_engine, list(target_points or []))
            score = float(objective_metrics["objective_score"])
        else:
            objective_metrics = _dyno_band_metrics(trial_engine, list(rpm_grid or []))
            if objective == "peak_power":
                score = -float(objective_metrics["peak_power_hp"])
            elif objective == "mean_torque_band":
                score = -float(objective_metrics["mean_torque_nm"])
            else:
                target_boost = getattr(trial_engine.turbo, "target_boost_kpa", None)
                if target_boost is None or float(target_boost) <= 0.0:
                    raise ValueError("boost_target_tracking objective requires turbo.target_boost_kpa > 0")
                achieved = float(objective_metrics.get("mean_boost_kpa", 0.0))
                score = abs(achieved - float(target_boost)) / max(abs(float(target_boost)), 1e-9)

        feasible = True
        violations: list[str] = []
        max_signal_mape = constraints.get("max_signal_mape", {})
        if isinstance(max_signal_mape, dict) and "signal_mape" in objective_metrics:
            for signal, limit in max_signal_mape.items():
                if signal in objective_metrics["signal_mape"] and float(objective_metrics["signal_mape"][signal]) > float(limit):
                    feasible = False
                    violations.append(f"{signal} mape > {float(limit):.6f}")
        min_peak = constraints.get("min_peak_power_hp")
        if min_peak is not None and float(objective_metrics.get("peak_power_hp", float("-inf"))) < float(min_peak):
            feasible = False
            violations.append(f"peak_power_hp < {float(min_peak):.6f}")
        min_mean_torque = constraints.get("min_mean_torque_nm")
        if min_mean_torque is not None and float(objective_metrics.get("mean_torque_nm", float("-inf"))) < float(min_mean_torque):
            feasible = False
            violations.append(f"mean_torque_nm < {float(min_mean_torque):.6f}")

        return {
            "params": {key: float(value) for key, value in candidate_params.items()},
            "score": float(score),
            "feasible": bool(feasible),
            "violations": violations,
            "objective_metrics": objective_metrics,
        }

    baseline_params = {param: _initial_guided_param_value(engine, param) for param in params}
    baseline = evaluate_candidate(baseline_params)

    param_grids = [_param_candidate_values(engine, param, param_bounds.get(param)) for param in params]
    combinations = [dict(zip(params, values)) for values in itertools.product(*param_grids)]
    rng = random.Random(int(seed))
    if len(combinations) > 1:
        head = combinations[:1]
        tail = combinations[1:]
        rng.shuffle(tail)
        combinations = head + tail

    candidates = [baseline]
    seen = {tuple(round(float(baseline["params"][param]), 8) for param in params)}
    for candidate in combinations:
        if len(candidates) >= max_evals:
            break
        key = tuple(round(float(candidate[param]), 8) for param in params)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(evaluate_candidate(candidate))

    feasible_candidates = [candidate for candidate in candidates if candidate["feasible"]]
    warnings: list[str] = []
    if feasible_candidates:
        best_candidate = min(feasible_candidates, key=lambda item: item["score"])
    else:
        best_candidate = min(candidates, key=lambda item: item["score"])
        warnings.append("No feasible candidate satisfied all requested constraints; best overall candidate is reported instead.")

    top_sorted = sorted(candidates, key=lambda item: item["score"])
    top_candidates = top_sorted[: min(5, len(top_sorted))]
    tradeoff_notes: list[str] = []
    if objective == "dataset_error" and "signal_mape" in baseline["objective_metrics"] and "signal_mape" in best_candidate["objective_metrics"]:
        improved = []
        worsened = []
        for signal, base_value in baseline["objective_metrics"]["signal_mape"].items():
            cand_value = best_candidate["objective_metrics"]["signal_mape"].get(signal)
            if cand_value is None:
                continue
            delta = float(base_value) - float(cand_value)
            if delta > 1e-6:
                improved.append(signal)
            elif delta < -1e-6:
                worsened.append(signal)
        if improved and worsened:
            tradeoff_notes.append(f"Best candidate improved {', '.join(improved)} but worsened {', '.join(worsened)}.")
        elif improved:
            tradeoff_notes.append(f"Best candidate improved {', '.join(improved)} without worsening scored dataset signals.")
        elif worsened:
            tradeoff_notes.append(f"Best candidate worsened {', '.join(worsened)} relative to the baseline on scored dataset signals.")

    top_scores = [float(candidate["score"]) for candidate in top_candidates]
    score_spread = max(top_scores) - min(top_scores) if top_scores else 0.0
    robustness = {
        "search_locality": "bounded_grid_search",
        "top_score_spread": float(score_spread),
        "fragility": "fragile_local" if score_spread < 1e-3 else "locally_stable",
        "top_candidate_count": int(len(top_candidates)),
    }
    if score_spread < 1e-3:
        warnings.append("Top candidates are very close in score; treat the reported optimum as local and potentially fragile.")

    optimization_problem = {
        "objective": objective,
        "params": params,
        "param_bounds": {key: [float(value[0]), float(value[1])] for key, value in param_bounds.items()},
        "constraints": constraints,
        "rpm_grid": [float(rpm) for rpm in (rpm_grid or [])],
        "signals_scored": sorted(
            baseline["objective_metrics"].get("signal_mape", {}).keys()
        ) if objective == "dataset_error" else ["power_hp", "torque_nm"] + (["boost_kpa"] if objective == "boost_target_tracking" else []),
    }

    best_payload = dict(best_candidate)
    best_payload["tradeoff_notes"] = tradeoff_notes
    best_payload["robustness"] = robustness

    return GuidedOptimizeReport(
        optimization_problem=optimization_problem,
        baseline=baseline,
        best_candidate=best_payload,
        candidates=top_candidates,
        warnings=warnings,
        evals_used=len(candidates),
        seed=int(seed),
        status="complete" if len(candidates) < max_evals else "max_evals",
    )


def load_target_points(path: str) -> list[dict]:
    path_obj = Path(path)
    if path_obj.is_dir():
        path_obj = path_obj / "target_curve.json"
    with open(path_obj, "r", encoding="utf-8") as handle:
        payload = json.loads(handle.read())
    points = payload.get("points", [])
    if not isinstance(points, list):
        raise ValueError("target points must be a list")
    return points
