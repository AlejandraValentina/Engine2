from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Optional

import numpy as np

from core.advanced.orchestrator import run_advanced_single_point

_DEFAULT_BOUNDS = {
    "fmep_pa": (20e3, 300e3),
    "eta_comb": (0.85, 1.0),
    "throttle_exponent": (0.5, 5.0),
    "fmep_curve_scale": (0.5, 2.0),
}
_DEFAULT_WEIGHTS = {"power": 1.0, "bsfc": 0.3, "fuel": 0.3}
_LOSS_EPS = 1e-9


def calibrate_to_curve(
    base_project_config: dict,
    target_points: list[dict],
    fit: dict,
    bounds: dict | None = None,
    max_outer_iters: int = 5,
    seed: int = 0,
) -> dict:
    if not target_points:
        raise ValueError("target_points must not be empty")
    if not base_project_config.get("calibration", {}).get("enabled", False):
        raise ValueError("calibration.enabled must be true to run calibrator")

    config_base = copy.deepcopy(base_project_config)
    fit_fmep = bool(fit.get("fmep", False))
    fit_eta = bool(fit.get("eta_comb", False))
    fit_throttle = bool(fit.get("throttle_k", False))

    if fit_eta and not _fuel_enabled(config_base):
        raise ValueError("simulation_settings.fuel.enabled must be true to fit eta_comb")
    if _targets_need_fuel(target_points) and not _fuel_enabled(config_base):
        raise ValueError("Fuel targets require simulation_settings.fuel.enabled=true")

    bound_cfg = _merge_bounds(bounds)

    fmep_param = _fmep_param_name(config_base)
    params: dict[str, float] = {}
    if fit_fmep:
        params[fmep_param] = _get_param_value(config_base, fmep_param)
    if fit_eta:
        params["eta_comb"] = _get_param_value(config_base, "eta_comb")
    if fit_throttle and _throttle_enabled(config_base):
        params["throttle_exponent"] = _get_param_value(config_base, "throttle_exponent")

    best_loss, best_preds = _evaluate_loss(config_base, params, target_points)
    history: list[dict] = [{"iter": 0, "params": dict(params), "loss": float(best_loss)}]

    for iter_idx in range(1, max_outer_iters + 1):
        improved = False
        for key in list(params.keys()):
            lo, hi = bound_cfg[key]
            params[key] = min(max(params[key], lo), hi)
            best_val, best_loss, best_preds = _optimize_param(
                config_base,
                params,
                key,
                lo,
                hi,
                target_points,
                best_loss,
                best_preds,
            )
            if best_val != params[key]:
                improved = True
            params[key] = best_val
        history.append({"iter": iter_idx, "params": dict(params), "loss": float(best_loss)})
        if not improved:
            break

    best_config = copy.deepcopy(config_base)
    _apply_params(best_config, params)
    predictions = best_preds if best_preds is not None else []
    return {
        "best_config": best_config,
        "best_loss": float(best_loss),
        "history": history,
        "predictions": predictions,
    }


def _optimize_param(
    base_config: dict,
    params: dict,
    key: str,
    lo: float,
    hi: float,
    target_points: list[dict],
    best_loss: float,
    best_preds: list[dict] | None,
) -> tuple[float, float, list[dict] | None]:
    grid = np.linspace(lo, hi, 9)
    best_val, best_loss, best_preds, grid_cache = _grid_search(
        base_config,
        params,
        key,
        grid,
        target_points,
        best_loss,
        best_preds,
        lo,
        hi,
    )

    best_idx = int(np.argmin([grid_cache[float(val)][0] for val in grid]))
    if 0 < best_idx < len(grid) - 1:
        a = float(grid[best_idx - 1])
        b = float(grid[best_idx + 1])
        best_val, best_loss, best_preds = _golden_section_search(
            base_config,
            params,
            key,
            a,
            b,
            target_points,
            best_val,
            best_loss,
            best_preds,
            lo=lo,
            hi=hi,
        )

    rounded = _round_param(key, best_val)
    if rounded != best_val:
        best_loss, best_preds = _evaluate_at(base_config, params, key, rounded, target_points, lo, hi)
        best_val = rounded
    return best_val, best_loss, best_preds


def _grid_search(
    base_config: dict,
    params: dict,
    key: str,
    grid: np.ndarray,
    target_points: list[dict],
    best_loss: float,
    best_preds: list[dict] | None,
    lo: float,
    hi: float,
) -> tuple[float, float, list[dict] | None, dict[float, tuple[float, list[dict]]]]:
    cache: dict[float, tuple[float, list[dict]]] = {}
    for value in grid:
        loss, preds = _evaluate_at(base_config, params, key, float(value), target_points, lo, hi)
        cache[float(value)] = (loss, preds)
        if loss < best_loss:
            best_loss = loss
            best_preds = preds
    best_val = min(cache, key=lambda val: (cache[val][0], val))
    best_loss = cache[best_val][0]
    best_preds = cache[best_val][1]
    return best_val, best_loss, best_preds, cache


def _evaluate_at(
    base_config: dict,
    params: dict,
    key: str,
    value: float,
    target_points: list[dict],
    lo: float | None = None,
    hi: float | None = None,
) -> tuple[float, list[dict]]:
    trial_params = dict(params)
    if lo is not None and hi is not None:
        value = min(max(float(value), lo), hi)
    trial_params[key] = float(value)
    return _evaluate_loss(base_config, trial_params, target_points)


def _golden_section_search(
    base_config: dict,
    params: dict,
    key: str,
    a: float,
    b: float,
    target_points: list[dict],
    best_val: float,
    best_loss: float,
    best_preds: list[dict] | None,
    max_iter: int = 32,
    tol: float = 1000.0,
    lo: float | None = None,
    hi: float | None = None,
) -> tuple[float, float, list[dict] | None]:
    a = float(min(a, b))
    b = float(max(a, b))
    if lo is not None and hi is not None:
        a = min(max(a, lo), hi)
        b = min(max(b, lo), hi)
    if abs(b - a) <= tol:
        return best_val, best_loss, best_preds
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    invphi = 1.0 / phi
    c = b - (b - a) * invphi
    d = a + (b - a) * invphi
    f_c, p_c = _evaluate_at(base_config, params, key, c, target_points, lo, hi)
    f_d, p_d = _evaluate_at(base_config, params, key, d, target_points, lo, hi)
    if f_c < best_loss:
        best_loss, best_val, best_preds = f_c, c, p_c
    if f_d < best_loss:
        best_loss, best_val, best_preds = f_d, d, p_d

    for _ in range(max_iter):
        if abs(b - a) <= tol:
            break
        if f_c <= f_d:
            b = d
            d = c
            f_d, p_d = f_c, p_c
            c = b - (b - a) * invphi
            f_c, p_c = _evaluate_at(base_config, params, key, c, target_points, lo, hi)
            if f_c < best_loss:
                best_loss, best_val, best_preds = f_c, c, p_c
        else:
            a = c
            c = d
            f_c, p_c = f_d, p_d
            d = a + (b - a) * invphi
            f_d, p_d = _evaluate_at(base_config, params, key, d, target_points, lo, hi)
            if f_d < best_loss:
                best_loss, best_val, best_preds = f_d, d, p_d

    return best_val, best_loss, best_preds


def _evaluate_loss(
    base_config: dict,
    params: dict,
    target_points: list[dict],
) -> tuple[float, list[dict]]:
    config = copy.deepcopy(base_config)
    _apply_params(config, params)
    preds = _predict_points(config, target_points)
    loss = _loss_from_predictions(preds, target_points)
    return loss, preds


def _predict_points(config: dict, target_points: list[dict]) -> list[dict]:
    indexed = list(enumerate(target_points))
    indexed.sort(key=lambda item: float(item[1].get("rpm", 0.0)))
    predictions: list[Optional[dict]] = [None] * len(target_points)
    state: Optional[dict] = None
    cycles = int(config.get("calibration", {}).get("cycles_per_point", 3))
    for idx, point in indexed:
        rpm = float(point["rpm"])
        pred, state = run_advanced_single_point(config, rpm, cycles=cycles, warm_start_state=state)
        predictions[idx] = pred
    return [pred for pred in predictions if pred is not None]


def _loss_from_predictions(preds: list[dict], targets: list[dict]) -> float:
    errs_main = []
    errs_bsfc = []
    errs_fuel = []
    for pred, tgt in zip(preds, targets):
        pred_val = _primary_value(pred, tgt)
        tgt_val = _target_value(tgt)
        errs_main.append(_norm_err(pred_val, tgt_val))

        if "bsfc_g_per_kwh" in tgt:
            errs_bsfc.append(_norm_err(pred.get("bsfc_g_per_kwh"), tgt.get("bsfc_g_per_kwh")))
        if "fuel_flow_kg_s" in tgt:
            errs_fuel.append(_norm_err(pred.get("fuel_flow_kg_s"), tgt.get("fuel_flow_kg_s")))

    rmse_main = _rmse(errs_main)
    rmse_bsfc = _rmse(errs_bsfc)
    rmse_fuel = _rmse(errs_fuel)
    return (
        _DEFAULT_WEIGHTS["power"] * rmse_main
        + _DEFAULT_WEIGHTS["bsfc"] * rmse_bsfc
        + _DEFAULT_WEIGHTS["fuel"] * rmse_fuel
    )


def _primary_value(pred: dict, tgt: dict) -> float:
    if "brake_power_w" in tgt:
        return float(pred.get("brake_power_w", 0.0))
    if "brake_torque_nm" in tgt:
        return float(pred.get("brake_torque_nm", 0.0))
    if "bmep_pa" in tgt:
        return float(pred.get("bmep_pa", 0.0))
    if "bmep_bar" in tgt:
        return float(pred.get("bmep_pa", 0.0)) / 1e5
    return float(pred.get("brake_power_w", 0.0))


def _target_value(tgt: dict) -> float:
    if "brake_power_w" in tgt:
        return float(tgt.get("brake_power_w", 0.0))
    if "brake_torque_nm" in tgt:
        return float(tgt.get("brake_torque_nm", 0.0))
    if "bmep_pa" in tgt:
        return float(tgt.get("bmep_pa", 0.0))
    if "bmep_bar" in tgt:
        return float(tgt.get("bmep_bar", 0.0))
    return float(tgt.get("brake_power_w", 0.0))


def _norm_err(pred: Optional[float], target: Optional[float]) -> float:
    if pred is None or target is None:
        return 0.0
    denom = max(abs(float(target)), _LOSS_EPS)
    return (float(pred) - float(target)) / denom


def _rmse(errs: list[float]) -> float:
    if not errs:
        return 0.0
    return math.sqrt(float(np.mean(np.square(errs))))


def _merge_bounds(bounds: dict | None) -> dict[str, tuple[float, float]]:
    merged: dict[str, tuple[float, float]] = dict(_DEFAULT_BOUNDS)
    if bounds:
        for key, value in bounds.items():
            if value is None:
                continue
            merged[key] = (float(value[0]), float(value[1]))
    return merged


def _fmep_param_name(config: dict) -> str:
    brake_model = config.get("brake_model", {})
    if "fmep_curve_scale" in brake_model and "fmep_pa" not in brake_model:
        return "fmep_curve_scale"
    return "fmep_pa"


def _get_param_value(config: dict, key: str) -> float:
    if key == "fmep_pa":
        return float(config.get("brake_model", {}).get("fmep_pa", 80e3))
    if key == "fmep_curve_scale":
        return float(config.get("brake_model", {}).get("fmep_curve_scale", 1.0))
    if key == "eta_comb":
        fuel_cfg = config.setdefault("simulation_settings", {}).setdefault("fuel", {})
        return float(fuel_cfg.get("eta_comb", 0.98))
    if key == "throttle_exponent":
        return float(config.get("throttle", {}).get("area_exponent", 2.0))
    raise KeyError(f"Unknown parameter '{key}'")


def _apply_params(config: dict, params: dict) -> None:
    brake_model = config.setdefault("brake_model", {})
    if "fmep_pa" in params:
        brake_model["fmep_pa"] = float(params["fmep_pa"])
    if "fmep_curve_scale" in params:
        brake_model["fmep_curve_scale"] = float(params["fmep_curve_scale"])
    if "eta_comb" in params:
        fuel_cfg = config.setdefault("simulation_settings", {}).setdefault("fuel", {})
        fuel_cfg["eta_comb"] = float(params["eta_comb"])
    if "throttle_exponent" in params:
        throttle = config.setdefault("throttle", {})
        throttle["area_exponent"] = float(params["throttle_exponent"])


def _throttle_enabled(config: dict) -> bool:
    return bool(config.get("throttle", {}).get("enabled", False))


def _fuel_enabled(config: dict) -> bool:
    return bool(config.get("simulation_settings", {}).get("fuel", {}).get("enabled", False))


def _targets_need_fuel(targets: list[dict]) -> bool:
    for tgt in targets:
        if "bsfc_g_per_kwh" in tgt or "fuel_flow_kg_s" in tgt:
            return True
    return False


def _round_param(key: str, value: float) -> float:
    if key == "fmep_pa":
        return round(value / 100.0) * 100.0
    if key == "fmep_curve_scale":
        return round(value, 4)
    if key == "eta_comb":
        return round(value, 4)
    if key == "throttle_exponent":
        return round(value, 4)
    return value
