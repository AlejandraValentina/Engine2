from __future__ import annotations

import json
from pathlib import Path

from core.auto_calibration import calibrate_engine
from core.engine_components import Engine


_PARAM_FIELD_MAP = {
    "ve_scale": "head.port_flow_efficiency",
    "friction_scale": "friction.global_scaling_factor",
    "burn_scale": "combustion.thermal_efficiency",
}


def _get_nested(mapping: dict, dotted: str):
    value = mapping
    for key in dotted.split("."):
        value = value[key]
    return value


def _load_target_payload(target_path: Path) -> tuple[dict, list[dict], dict | None]:
    if target_path.is_dir():
        dataset_dir = target_path
        target_file = dataset_dir / "target_curve.json"
    else:
        target_file = target_path
        dataset_dir = target_file.parent

    payload = json.loads(target_file.read_text(encoding="utf-8"))
    points = payload.get("points") or payload.get("targets") or []
    if not isinstance(points, list) or not points:
        raise ValueError("target file must include non-empty 'points' list")

    metadata_path = dataset_dir / "metadata.json"
    dataset_meta = None
    if metadata_path.exists():
        dataset_meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    return payload, points, dataset_meta


def _build_param_trace(engine_before: Engine, engine_after: Engine, params_final: dict) -> dict:
    before = engine_before.to_dict()
    after = engine_after.to_dict()
    trace = {}
    for param, scale in params_final.items():
        field = _PARAM_FIELD_MAP.get(param)
        if field is None:
            continue
        trace[param] = {
            "field": field,
            "scale": float(scale),
            "value_before": _get_nested(before, field),
            "value_after": _get_nested(after, field),
        }
    return trace


def run_reproducible_calibration(
    engine: Engine,
    engine_raw: dict,
    *,
    base_engine_path: Path,
    target_path: Path,
    params: list[str],
    max_evals: int,
) -> tuple[dict, dict]:
    _, points, dataset_meta = _load_target_payload(target_path)
    report = calibrate_engine(engine, points, params, max_evals)

    calibrated_engine = Engine.from_dict(engine.to_dict())
    from core.auto_calibration import _apply_scales  # local import to reuse existing calibration behavior

    _apply_scales(calibrated_engine, report.params_final)
    calibrated_raw = calibrated_engine.to_dict()

    output = {
        "preset_base_path": str(base_engine_path),
        "target_path": str(target_path),
        "dataset": dataset_meta,
        "params_initial": report.params_initial,
        "params_final": report.params_final,
        "parameter_values": _build_param_trace(engine, calibrated_engine, report.params_final),
        "error_initial": float(report.error_initial),
        "error_final": float(report.error_final),
        "evals_used": int(report.evals_used),
        "status": report.status,
        "artifacts": {
            "calibrated_engine": "calibrated_engine.json",
            "benchmark_before": None,
            "benchmark_after": None,
        },
    }
    return output, calibrated_raw
