from __future__ import annotations

import json
from pathlib import Path

from core.auto_calibration import _apply_scales, calibrate_engine
from core.engine_components import Engine
from pywavedyn.analysis_contract import (
    REPORT_TYPE_STAGED_CALIBRATION,
    apply_analysis_envelope,
    build_report_context,
)
from pywavedyn.bench import evaluate_with_engine
from pywavedyn.combustion_mode import summarize_combustion_mode
from pywavedyn.engineering_diagnostics import diagnose_staged_calibration_report


STAGE_DEFS = [
    {
        "stage_name": "airflow_ve",
        "params": ["ve_scale"],
        "signals": ["torque_nm", "power_hp"],
        "notes": "Calibrates volumetric-efficiency proxy through ve_scale.",
    },
    {
        "stage_name": "friction",
        "params": ["friction_scale"],
        "signals": ["torque_nm", "power_hp"],
        "notes": "Calibrates mechanical losses through friction_scale.",
    },
    {
        "stage_name": "combustion",
        "params": ["burn_scale"],
        "signals": ["power_hp", "torque_nm"],
        "notes": "Current flow adjusts thermal-efficiency proxy via burn_scale; direct phasing calibration is not yet exposed.",
    },
    {
        "stage_name": "turbo",
        "params": [],
        "signals": ["boost_kpa", "map_kpa", "power_hp", "torque_nm"],
        "notes": "Calibrates supported turbo level/timing parameters when boost evidence and exposed turbo controls are available.",
    },
    {
        "stage_name": "thermal",
        "params": [],
        "signals": ["egt_c"],
        "notes": "Skipped unless a physically-supported thermal correction parameter set exists in the current core.",
    },
]

ADAPTIVE_STAGE_DEF = {
    "stage_name": "combustion_adaptive",
    "params": ["adaptive_duration_scale", "adaptive_ca50_offset_deg"],
    "signals": ["power_hp", "torque_nm"],
    "notes": "Calibrates the adaptive combustion global schedule through duration_scale and ca50_offset_deg when adaptive combustion is enabled.",
}


def _load_dataset(dataset_dir: Path) -> tuple[dict, list[dict]]:
    meta = json.loads((dataset_dir / "metadata.json").read_text(encoding="utf-8"))
    target = json.loads((dataset_dir / "target_curve.json").read_text(encoding="utf-8"))
    points = target.get("points", [])
    if not isinstance(points, list) or not points:
        raise ValueError("target_curve.json must include non-empty points list")
    return meta, points


def _stage_points(points: list[dict], allowed_signals: list[str]) -> list[dict]:
    filtered: list[dict] = []
    for point in points:
        row = {"rpm": float(point["rpm"])}
        for signal in allowed_signals:
            if signal in point:
                row[signal] = point[signal]
        if len(row) > 1:
            filtered.append(row)
    return filtered


def _metric_summary(report) -> dict:
    summary = {
        "torque_mape": float(report.errors["torque_nm"]["mape"]),
        "power_mape": float(report.errors["power_hp"]["mape"]),
        "total_mape": float(report.errors["total_mape"]),
        "contract_pass": bool(report.contract["pass"]),
    }
    if "optional_signals" in report.errors:
        summary["optional_signals"] = {
            signal: {
                "mape": float(data["mape"]),
                "count": int(data["count"]),
            }
            for signal, data in report.errors["optional_signals"].items()
        }
    return summary


def run_staged_calibration(
    engine: Engine,
    engine_raw: dict,
    *,
    base_engine_path: Path,
    dataset_dir: Path,
    max_evals_per_stage: int,
) -> tuple[dict, dict, dict, dict]:
    dataset_meta, points = _load_dataset(dataset_dir)
    current_engine = Engine.from_dict(engine.to_dict())
    current_raw = current_engine.to_dict()
    bench_before = evaluate_with_engine(current_engine, current_raw, dataset_dir).to_dict()
    current_metrics = _metric_summary(evaluate_with_engine(current_engine, current_raw, dataset_dir))
    stages: list[dict] = []
    final_params: dict[str, float] = {}
    stage_defs = list(STAGE_DEFS)
    adaptive_enabled = bool((getattr(current_engine.combustion, "adaptive_model", {}) or {}).get("enabled", False))
    stage_defs.insert(3, ADAPTIVE_STAGE_DEF)

    for stage_def in stage_defs:
        stage_name = str(stage_def["stage_name"])
        params = list(stage_def["params"])
        notes = str(stage_def["notes"])
        if stage_name == "turbo":
            turbo_params: list[str] = []
            if current_engine.turbo.enabled:
                if current_engine.turbo.target_boost_kpa is not None or current_engine.turbo.target_pr is not None:
                    turbo_params.append("turbo_target_boost_scale")
                if bool((getattr(current_engine.turbo, "response_model", {}) or {}).get("enabled", False)):
                    turbo_params.append("turbo_spool_rpm_offset")
            params = turbo_params
        allowed_signals = list(stage_def["signals"])
        stage_points = _stage_points(points, allowed_signals)
        signals_used = sorted({key for point in stage_points for key in point if key != "rpm"})

        stage_entry = {
            "stage_name": stage_name,
            "params_touched": params,
            "signals_used": signals_used,
            "before_metrics": dict(current_metrics),
            "after_metrics": dict(current_metrics),
            "accepted": False,
            "notes": notes,
        }

        if not params:
            if stage_name == "turbo" and not current_engine.turbo.enabled:
                stage_entry["notes"] += " Stage omitted because the engine is not turbocharged."
            else:
                stage_entry["notes"] += " Stage omitted because no supported calibration parameter is currently exposed."
            stages.append(stage_entry)
            continue

        if stage_name == "combustion_adaptive" and not adaptive_enabled:
            stage_entry["notes"] += " Stage omitted because combustion.adaptive_model.enabled is false."
            stages.append(stage_entry)
            continue

        if not stage_points:
            stage_entry["notes"] += " Stage omitted because the dataset does not contain the required signals."
            stages.append(stage_entry)
            continue

        report = calibrate_engine(current_engine, stage_points, params, max_evals_per_stage)
        candidate_engine = Engine.from_dict(current_engine.to_dict())
        _apply_scales(candidate_engine, report.params_final)
        candidate_raw = candidate_engine.to_dict()
        candidate_bench = evaluate_with_engine(candidate_engine, candidate_raw, dataset_dir)
        candidate_metrics = _metric_summary(candidate_bench)

        stage_entry["before_metrics"]["objective_filtered"] = float(report.error_initial)
        stage_entry["after_metrics"] = dict(candidate_metrics)
        stage_entry["after_metrics"]["objective_filtered"] = float(report.error_final)

        if float(report.error_final) + 1e-12 < float(report.error_initial):
            stage_entry["accepted"] = True
            current_engine = candidate_engine
            current_raw = candidate_raw
            current_metrics = candidate_metrics
            for key, value in report.params_final.items():
                final_params[key] = float(value)
        else:
            stage_entry["notes"] += " Candidate was rejected because filtered objective did not improve."

        stages.append(stage_entry)

    bench_after = evaluate_with_engine(current_engine, current_raw, dataset_dir).to_dict()
    output = {
        "preset_base_path": str(base_engine_path),
        "dataset": dataset_meta,
        "signal_evidence": dict(bench_before.get("signal_evidence", {})),
        "combustion_before": summarize_combustion_mode(engine),
        "combustion_after": summarize_combustion_mode(current_engine),
        "stages": stages,
        "final_params": final_params,
        "artifacts": {
            "calibrated_engine": "calibrated_engine.json",
            "benchmark_before": "benchmark_before.json",
            "benchmark_after": "benchmark_after.json",
        },
    }
    output["diagnostics"] = diagnose_staged_calibration_report(output, bench_before=bench_before, bench_after=bench_after)
    apply_analysis_envelope(
        output,
        report_type=REPORT_TYPE_STAGED_CALIBRATION,
        context=build_report_context(dataset=dataset_meta, base_engine_path=base_engine_path),
    )
    return output, current_raw, bench_before, bench_after
