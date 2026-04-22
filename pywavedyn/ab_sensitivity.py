from __future__ import annotations

import copy
from pathlib import Path

from core.auto_calibration import _apply_scales, _initial_param_value
from core.engine_components import Engine
from pywavedyn.analysis_contract import (
    REPORT_TYPE_AB_COMPARE,
    REPORT_TYPE_SENSITIVITY_LOCAL,
    apply_analysis_envelope,
    build_report_context,
)
from pywavedyn.analysis_labels import robustness_level
from pywavedyn.bench import evaluate_with_engine
from pywavedyn.combustion_mode import summarize_combustion_mode
from pywavedyn.validation_compare import (
    OPTIONAL_VALIDATION_SIGNALS,
    apply_turbo_incremental_mode,
    compare_feature_summaries,
    report_feature_summary,
    _summarize_turbo_incremental,
)


SENSITIVITY_PARAM_DEFS = {
    "ve_scale": {
        "interpretation": "Volumetric-efficiency proxy scaling.",
        "kind": "multiplier",
        "multipliers": [0.9, 1.1],
    },
    "friction_scale": {
        "interpretation": "Mechanical friction-loss scaling.",
        "kind": "multiplier",
        "multipliers": [0.9, 1.1],
    },
    "burn_scale": {
        "interpretation": "Combustion thermal-efficiency proxy scaling.",
        "kind": "multiplier",
        "multipliers": [0.9, 1.1],
    },
    "adaptive_duration_scale": {
        "interpretation": "Global adaptive combustion duration scale.",
        "kind": "absolute_scale_about_base",
        "relative": [0.9, 1.1],
    },
    "adaptive_ca50_offset_deg": {
        "interpretation": "Global adaptive combustion CA50 offset.",
        "kind": "absolute_offset_about_base",
        "offsets": [-2.0, 2.0],
    },
    "turbo_target_boost_scale": {
        "interpretation": "Turbo target boost scaling around the configured target.",
        "kind": "multiplier",
        "multipliers": [0.9, 1.1],
    },
    "turbo_spool_rpm_offset": {
        "interpretation": "Turbo spool timing offset around the configured response model.",
        "kind": "offset_about_zero",
        "offsets": [-500.0, 500.0],
    },
}


def _engine_feature_state(engine: Engine) -> dict:
    return {
        "combustion": summarize_combustion_mode(engine),
        "turbo_incremental": _summarize_turbo_incremental(engine),
    }


def _report_summary(engine: Engine, report: dict, *, label: str) -> dict:
    return report_feature_summary(label, report, feature_state=_engine_feature_state(engine))


def run_ab_compare(
    engine_a: Engine,
    raw_a: dict,
    engine_b: Engine,
    raw_b: dict,
    *,
    dataset_dir: Path,
    label_a: str,
    label_b: str,
) -> dict:
    dataset_dir = dataset_dir.resolve()
    report_a = evaluate_with_engine(engine_a, raw_a, dataset_dir).to_dict()
    report_b = evaluate_with_engine(engine_b, raw_b, dataset_dir).to_dict()
    summary_a = _report_summary(engine_a, report_a, label=label_a)
    summary_b = _report_summary(engine_b, report_b, label=label_b)
    comparison = compare_feature_summaries(summary_a, summary_b, label_a=label_a, label_b=label_b)
    payload = {
        "dataset": {
            "dataset_id": str(report_a["dataset"]["dataset_id"]),
            "engine_id": str(report_a["dataset"]["engine_id"]),
            "preset_path": str(report_a["dataset"]["preset_path"]),
            "path": str(dataset_dir),
        },
        "signal_coverage": {
            "dataset_signals": list(report_a.get("signal_coverage", {}).get("dataset_signals", [])),
            "compared_signals_union": sorted(
                set(report_a.get("signal_coverage", {}).get("compared_signals", []))
                | set(report_b.get("signal_coverage", {}).get("compared_signals", []))
            ),
            "skipped_signals_union": sorted(
                set(report_a.get("signal_coverage", {}).get("skipped_signals", []))
                | set(report_b.get("signal_coverage", {}).get("skipped_signals", []))
            ),
        },
        "signal_evidence": dict(report_a.get("signal_evidence", {})),
        "comparison": comparison,
    }
    return apply_analysis_envelope(
        payload,
        report_type=REPORT_TYPE_AB_COMPARE,
        context=build_report_context(dataset=payload["dataset"]),
    )


def _perturbation_values(engine: Engine, param: str) -> list[tuple[str, float]]:
    cfg = SENSITIVITY_PARAM_DEFS[param]
    kind = str(cfg["kind"])
    if kind == "multiplier":
        return [("minus", float(cfg["multipliers"][0])), ("plus", float(cfg["multipliers"][1]))]
    base = float(_initial_param_value(engine, param))
    if kind == "absolute_scale_about_base":
        values = [max(base * float(cfg["relative"][0]), 0.1), max(base * float(cfg["relative"][1]), 0.1)]
        return [("minus", float(values[0])), ("plus", float(values[1]))]
    if kind == "absolute_offset_about_base":
        offsets = list(cfg["offsets"])
        return [("minus", base + float(offsets[0])), ("plus", base + float(offsets[1]))]
    if kind == "offset_about_zero":
        offsets = list(cfg["offsets"])
        return [("minus", float(offsets[0])), ("plus", float(offsets[1]))]
    raise ValueError(f"Unsupported sensitivity perturbation kind '{kind}'")


def _param_support_reason(engine: Engine, param: str) -> str | None:
    if param in {"adaptive_duration_scale", "adaptive_ca50_offset_deg"}:
        adaptive_cfg = getattr(engine.combustion, "adaptive_model", {}) or {}
        if not bool(adaptive_cfg.get("enabled", False)):
            return "Adaptive combustion sensitivity requires combustion.adaptive_model.enabled = true."
    if param == "turbo_target_boost_scale":
        if not bool(engine.turbo.enabled):
            return "Turbo target sensitivity requires a turbocharged engine."
        if engine.turbo.target_boost_kpa is None and engine.turbo.target_pr is None:
            return "Turbo target sensitivity requires target_boost_kpa or target_pr."
    if param == "turbo_spool_rpm_offset":
        response_cfg = getattr(engine.turbo, "response_model", {}) or {}
        if not bool(engine.turbo.enabled):
            return "Turbo spool sensitivity requires a turbocharged engine."
        if not bool(response_cfg.get("enabled", False)):
            return "Turbo spool sensitivity requires turbo.response_model.enabled = true."
    return None


def _apply_param(engine: Engine, param: str, value: float) -> None:
    _apply_scales(engine, {param: float(value)})


def run_local_sensitivity(
    engine: Engine,
    engine_raw: dict,
    *,
    dataset_dir: Path,
    params: list[str],
) -> dict:
    dataset_dir = dataset_dir.resolve()
    baseline_engine = Engine.from_dict(engine.to_dict())
    baseline_raw = copy.deepcopy(engine_raw)
    baseline_report = evaluate_with_engine(baseline_engine, baseline_raw, dataset_dir).to_dict()
    baseline = _report_summary(baseline_engine, baseline_report, label="baseline")
    param_results: list[dict] = []

    for param in params:
        if param not in SENSITIVITY_PARAM_DEFS:
            raise ValueError(f"Unsupported sensitivity param '{param}'")
        support_reason = _param_support_reason(baseline_engine, param)
        if support_reason is not None:
            param_results.append(
                {
                    "param": param,
                    "supported": False,
                    "interpretation": SENSITIVITY_PARAM_DEFS[param]["interpretation"],
                    "note": support_reason,
                    "perturbations": [],
                    "influence_by_signal": {},
                    "overall_influence_score": None,
                    "tradeoff_detected": False,
                }
            )
            continue

        perturbation_results: list[dict] = []
        influence_by_signal: dict[str, float] = {}
        tradeoff_detected = False
        for label, value in _perturbation_values(baseline_engine, param):
            candidate_engine = Engine.from_dict(baseline_engine.to_dict())
            candidate_raw = copy.deepcopy(baseline_raw)
            _apply_param(candidate_engine, param, value)
            candidate_report = evaluate_with_engine(candidate_engine, candidate_raw, dataset_dir).to_dict()
            candidate_summary = _report_summary(candidate_engine, candidate_report, label=f"{param}_{label}")
            comparison = compare_feature_summaries(baseline, candidate_summary, label_a="baseline", label_b=f"{param}_{label}")
            delta = comparison["delta_a_to_b"]
            if delta.get("improved_signals") and delta.get("worsened_signals"):
                tradeoff_detected = True
            for signal, signal_delta in delta.get("by_signal", {}).items():
                influence_by_signal[signal] = max(
                    abs(float(signal_delta["delta_mape"])),
                    influence_by_signal.get(signal, 0.0),
                )
            perturbation_results.append(
                {
                    "label": label,
                    "value": float(value),
                    "comparison_vs_baseline": comparison,
                }
            )

        overall_influence = max(influence_by_signal.values(), default=0.0)
        param_results.append(
            {
                "param": param,
                "supported": True,
                "interpretation": SENSITIVITY_PARAM_DEFS[param]["interpretation"],
                "note": "Local two-sided perturbation around the current configuration.",
                "perturbations": perturbation_results,
                "influence_by_signal": {
                    signal: {
                        "max_abs_delta_mape": float(score),
                        "robustness_level": robustness_level(float(score)),
                    }
                    for signal, score in sorted(influence_by_signal.items())
                },
                "overall_influence_score": float(overall_influence),
                "tradeoff_detected": bool(tradeoff_detected),
            }
        )

    rankings_by_signal: dict[str, list[dict]] = {}
    robustness_by_signal: dict[str, dict] = {}
    for signal in ("torque_nm", "power_hp", *OPTIONAL_VALIDATION_SIGNALS):
        ranking = []
        for result in param_results:
            if not result.get("supported", False):
                continue
            signal_info = result.get("influence_by_signal", {}).get(signal)
            if signal_info is None:
                continue
            ranking.append(
                {
                    "param": str(result["param"]),
                    "max_abs_delta_mape": float(signal_info["max_abs_delta_mape"]),
                    "tradeoff_detected": bool(result.get("tradeoff_detected", False)),
                }
            )
        ranking.sort(key=lambda item: item["max_abs_delta_mape"], reverse=True)
        if ranking:
            rankings_by_signal[signal] = ranking
            robustness_by_signal[signal] = {
                "top_param": ranking[0]["param"],
                "max_abs_delta_mape": float(ranking[0]["max_abs_delta_mape"]),
                "level": robustness_level(float(ranking[0]["max_abs_delta_mape"])),
            }

    payload = {
        "dataset": {
            "dataset_id": str(baseline_report["dataset"]["dataset_id"]),
            "engine_id": str(baseline_report["dataset"]["engine_id"]),
            "preset_path": str(baseline_report["dataset"]["preset_path"]),
            "path": str(dataset_dir),
        },
        "signal_evidence": dict(baseline_report.get("signal_evidence", {})),
        "baseline": baseline,
        "params": param_results,
        "summary": {
            "rankings_by_signal": rankings_by_signal,
            "robustness_by_signal": robustness_by_signal,
        },
    }
    return apply_analysis_envelope(
        payload,
        report_type=REPORT_TYPE_SENSITIVITY_LOCAL,
        context=build_report_context(dataset=payload["dataset"]),
    )
