from __future__ import annotations

import copy
from pathlib import Path

from core.engine_components import Engine
from pywavedyn.analysis_evidence import build_signal_evidence
from pywavedyn.analysis_contract import (
    REPORT_TYPE_VALIDATION_COMPARE,
    apply_analysis_envelope,
    build_shared_case_context,
)
from pywavedyn.analysis_labels import (
    COMPARISON_OUTCOME_DEFAULT,
    COMPARISON_OUTCOMES,
    empty_comparison_outcome_counts,
    normalize_comparison_outcome,
)
from pywavedyn.bench import evaluate_with_engine
from pywavedyn.combustion_mode import apply_adaptive_combustion_mode, summarize_combustion_mode
from pywavedyn.staged_calibration import run_staged_calibration


OPTIONAL_VALIDATION_SIGNALS = ("boost_kpa", "map_kpa", "lambda", "afr")
OUTCOME_ORDER = COMPARISON_OUTCOMES


def _summarize_turbo_incremental(engine: Engine, *, requested_mode: str = "as_is") -> dict:
    response_cfg = getattr(engine.turbo, "response_model", {}) or {}
    summary = {
        "turbo_incremental_requested": str(requested_mode),
        "turbo_enabled": bool(engine.turbo.enabled),
        "turbo_incremental_enabled": bool(response_cfg.get("enabled", False)),
        "turbo_response_parameters": {},
        "turbo_response_config_keys": sorted(response_cfg.keys()),
    }
    for key in ("spool_rpm", "spool_width_rpm", "flow_ref_kg_s", "flow_width_kg_s", "min_response"):
        if key in response_cfg:
            summary["turbo_response_parameters"][key] = float(response_cfg[key])
    return summary


def apply_turbo_incremental_mode(
    engine: Engine,
    engine_raw: dict,
    *,
    mode: str = "as_is",
) -> tuple[Engine, dict, dict]:
    requested_mode = str(mode or "as_is").strip().lower()
    if requested_mode not in {"as_is", "on", "off"}:
        raise ValueError("turbo incremental mode must be one of ['as_is', 'off', 'on']")

    adjusted_engine = Engine.from_dict(engine.to_dict())
    adjusted_raw = copy.deepcopy(engine_raw)

    turbo_raw = adjusted_raw.setdefault("turbo", {})
    response_cfg = dict(getattr(adjusted_engine.turbo, "response_model", {}) or {})
    if "response_model" in turbo_raw and isinstance(turbo_raw["response_model"], dict):
        response_cfg.update(turbo_raw["response_model"])

    if requested_mode == "on":
        response_cfg["enabled"] = True
    elif requested_mode == "off":
        response_cfg["enabled"] = False

    adjusted_engine.turbo.response_model = response_cfg
    if response_cfg:
        turbo_raw["response_model"] = response_cfg
    else:
        turbo_raw.pop("response_model", None)

    summary = _summarize_turbo_incremental(adjusted_engine, requested_mode=requested_mode)
    return adjusted_engine, adjusted_raw, summary


def _signal_mape(report: dict, signal: str) -> float | None:
    errors = report.get("errors", {})
    if signal in {"torque_nm", "power_hp"}:
        entry = errors.get(signal, {})
        if "mape" in entry:
            return float(entry["mape"])
        return None
    optional = errors.get("optional_signals", {})
    entry = optional.get(signal, {})
    if "mape" in entry:
        return float(entry["mape"])
    return None


def _feature_metrics(report: dict) -> dict:
    metrics = {
        "torque_nm": {"mape": float(report["errors"]["torque_nm"]["mape"])},
        "power_hp": {"mape": float(report["errors"]["power_hp"]["mape"])},
        "total_mape": float(report["errors"]["total_mape"]),
    }
    for signal in OPTIONAL_VALIDATION_SIGNALS:
        value = _signal_mape(report, signal)
        if value is not None:
            metrics[signal] = {"mape": float(value)}
    return metrics


def _feature_summary(
    feature_name: str,
    report: dict,
    *,
    feature_state: dict | None = None,
) -> dict:
    coverage = report.get("signal_coverage", {})
    signal_evidence = report.get("signal_evidence")
    if not isinstance(signal_evidence, dict):
        signal_evidence = build_signal_evidence(
            dataset_signals=coverage.get("dataset_signals", []),
            compared_signals=coverage.get("compared_signals", []),
            skipped_signals=coverage.get("skipped_signals", []),
        )
    return {
        "feature_name": feature_name,
        "evaluated": True,
        "supported": True,
        "feature_state": feature_state or {},
        "contract_pass": bool(report.get("contract", {}).get("pass", False)),
        "metrics_by_signal": _feature_metrics(report),
        "signal_coverage": {
            "compared_signals": list(coverage.get("compared_signals", [])),
            "skipped_signals": list(coverage.get("skipped_signals", [])),
        },
        "signal_evidence": signal_evidence,
        "diagnostics": list(report.get("diagnostics", [])),
    }


def report_feature_summary(
    feature_name: str,
    report: dict,
    *,
    feature_state: dict | None = None,
) -> dict:
    return _feature_summary(feature_name, report, feature_state=feature_state)


def _unsupported_feature_summary(
    feature_name: str,
    *,
    note: str,
    feature_state: dict | None = None,
    signal_evidence: dict | None = None,
) -> dict:
    return {
        "feature_name": feature_name,
        "evaluated": False,
        "supported": False,
        "feature_state": feature_state or {},
        "contract_pass": None,
        "metrics_by_signal": {},
        "signal_coverage": {"compared_signals": [], "skipped_signals": []},
        "signal_evidence": signal_evidence or {"dataset_signals": [], "compared_signals": [], "skipped_signals": [], "groups": {}, "limitations": []},
        "diagnostics": [],
        "delta_vs_baseline": {"signals_compared": [], "improved_signals": [], "worsened_signals": [], "unchanged_signals": []},
        "outcome": COMPARISON_OUTCOME_DEFAULT,
        "note": note,
    }


def _delta_summary(baseline: dict, candidate: dict) -> dict:
    baseline_metrics = baseline.get("metrics_by_signal", {})
    candidate_metrics = candidate.get("metrics_by_signal", {})
    signals = sorted(set(baseline_metrics) & set(candidate_metrics) - {"total_mape"})
    deltas: dict[str, dict] = {}
    improved: list[str] = []
    worsened: list[str] = []
    unchanged: list[str] = []
    for signal in signals:
        base_mape = float(baseline_metrics[signal]["mape"])
        cand_mape = float(candidate_metrics[signal]["mape"])
        delta = base_mape - cand_mape
        deltas[signal] = {
            "baseline_mape": base_mape,
            "candidate_mape": cand_mape,
            "delta_mape": delta,
        }
        if delta > 1e-6:
            improved.append(signal)
        elif delta < -1e-6:
            worsened.append(signal)
        else:
            unchanged.append(signal)
    total_delta = float(baseline_metrics.get("total_mape", 0.0)) - float(candidate_metrics.get("total_mape", 0.0))
    return {
        "signals_compared": signals,
        "by_signal": deltas,
        "total_mape": {
            "baseline": float(baseline_metrics.get("total_mape", 0.0)),
            "candidate": float(candidate_metrics.get("total_mape", 0.0)),
            "delta": total_delta,
        },
        "improved_signals": improved,
        "worsened_signals": worsened,
        "unchanged_signals": unchanged,
    }


def _case_outcome(baseline: dict, candidate: dict, delta: dict) -> str:
    improved = list(delta.get("improved_signals", []))
    worsened = list(delta.get("worsened_signals", []))
    if not delta.get("signals_compared"):
        return COMPARISON_OUTCOME_DEFAULT
    base_pass = bool(baseline.get("contract_pass", False))
    cand_pass = bool(candidate.get("contract_pass", False))
    total_delta = float(delta.get("total_mape", {}).get("delta", 0.0))
    if improved and not worsened:
        return "improved"
    if improved and worsened:
        if not base_pass and cand_pass:
            return "improved"
        if total_delta > 1e-6:
            return "partial_improvement"
        return "tradeoff"
    if not improved and worsened:
        return "no_clear_benefit"
    if total_delta > 1e-6 and cand_pass != base_pass:
        return "partial_improvement"
    return "no_clear_benefit"


def _case_note(feature_name: str, baseline: dict, candidate: dict, delta: dict, outcome: str) -> str:
    improved = ", ".join(delta.get("improved_signals", []))
    worsened = ", ".join(delta.get("worsened_signals", []))
    if outcome == "improved":
        return f"{feature_name} reduced the compared error without worsening any scored signal."
    if outcome == "partial_improvement":
        if worsened:
            return f"{feature_name} improved {improved or 'some signals'} but worsened {worsened}, so the benefit is only partial."
        return f"{feature_name} improved some scored metrics, but not enough to count as a clean overall gain."
    if outcome == "tradeoff":
        return f"{feature_name} improved {improved or 'some signals'} while worsening {worsened or 'others'}, so this looks like a tradeoff rather than a clean win."
    if outcome == "no_clear_benefit":
        return f"{feature_name} did not show a clear benefit against the currently scored signals."
    return f"{feature_name} could not be concluded from the signals currently available in this case."


def _attach_outcome(baseline: dict, candidate: dict) -> dict:
    delta = _delta_summary(baseline, candidate)
    outcome = _case_outcome(baseline, candidate, delta)
    enriched = dict(candidate)
    enriched["delta_vs_baseline"] = delta
    enriched["outcome"] = outcome
    enriched["note"] = _case_note(candidate["feature_name"], baseline, candidate, delta, outcome)
    return enriched


def compare_feature_summaries(summary_a: dict, summary_b: dict, *, label_a: str, label_b: str) -> dict:
    delta = _delta_summary(summary_a, summary_b)
    outcome = _case_outcome(summary_a, summary_b, delta)
    return {
        "labels": {"a": label_a, "b": label_b},
        "a": summary_a,
        "b": summary_b,
        "delta_a_to_b": delta,
        "outcome": outcome,
        "note": _case_note(f"{label_a} vs {label_b}", summary_a, summary_b, delta, outcome),
    }


def _baseline_payload(report: dict, *, combustion_state: dict, turbo_state: dict) -> dict:
    payload = _feature_summary(
        "baseline",
        report,
        feature_state={
            "combustion": combustion_state,
            "turbo_incremental": turbo_state,
        },
    )
    payload["note"] = "Baseline uses the engine configuration as supplied to this validation run."
    return payload


def _staged_feature_payload(staged_report: dict, bench_after: dict) -> dict:
    payload = _feature_summary(
        "staged_after",
        bench_after,
        feature_state={
            "final_params": dict(staged_report.get("final_params", {})),
            "stage_outcomes": [
                {
                    "stage_name": str(stage.get("stage_name", "")),
                    "accepted": bool(stage.get("accepted", False)),
                    "signals_used": list(stage.get("signals_used", [])),
                    "notes": str(stage.get("notes", "")),
                }
                for stage in staged_report.get("stages", [])
            ],
        },
    )
    payload["staged_calibration"] = {
        "diagnostics": list(staged_report.get("diagnostics", [])),
        "artifacts": dict(staged_report.get("artifacts", {})),
        "artifacts_materialized": False,
    }
    return payload


def run_validation_case(
    engine: Engine,
    engine_raw: dict,
    *,
    base_engine_path: Path,
    dataset_dir: Path,
    include_adaptive_toggle: bool,
    include_turbo_toggle: bool,
    include_staged_calibration: bool,
    max_evals_per_stage: int,
) -> dict:
    dataset_dir = dataset_dir.resolve()
    baseline_engine = Engine.from_dict(engine.to_dict())
    baseline_raw = copy.deepcopy(engine_raw)
    baseline_report = evaluate_with_engine(baseline_engine, baseline_raw, dataset_dir).to_dict()
    baseline = _baseline_payload(
        baseline_report,
        combustion_state=summarize_combustion_mode(baseline_engine),
        turbo_state=_summarize_turbo_incremental(baseline_engine),
    )

    case_payload = {
        "dataset": {
            "dataset_id": str(baseline_report["dataset"]["dataset_id"]),
            "engine_id": str(baseline_report["dataset"]["engine_id"]),
            "preset_path": str(baseline_report["dataset"]["preset_path"]),
            "path": str(dataset_dir),
        },
        "signal_coverage": dict(baseline_report.get("signal_coverage", {})),
        "signal_evidence": dict(baseline_report.get("signal_evidence", {})),
        "baseline": baseline,
        "features": {},
    }

    if include_adaptive_toggle:
        for mode in ("on", "off"):
            feature_name = f"adaptive_{mode}"
            candidate_engine, candidate_raw, summary = apply_adaptive_combustion_mode(
                baseline_engine,
                baseline_raw,
                mode=mode,
            )
            candidate_report = evaluate_with_engine(candidate_engine, candidate_raw, dataset_dir).to_dict()
            feature = _feature_summary(
                feature_name,
                candidate_report,
                feature_state={"combustion": summary},
            )
            case_payload["features"][feature_name] = _attach_outcome(baseline, feature)

    if include_turbo_toggle:
        if not bool(baseline_engine.turbo.enabled):
            case_payload["features"]["turbo_incremental_on"] = _unsupported_feature_summary(
                "turbo_incremental_on",
                note="Turbo incremental validation was not run because the engine is not turbocharged.",
                feature_state={"turbo_incremental": _summarize_turbo_incremental(baseline_engine)},
                signal_evidence=dict(baseline_report.get("signal_evidence", {})),
            )
            case_payload["features"]["turbo_incremental_off"] = _unsupported_feature_summary(
                "turbo_incremental_off",
                note="Turbo incremental validation was not run because the engine is not turbocharged.",
                feature_state={"turbo_incremental": _summarize_turbo_incremental(baseline_engine)},
                signal_evidence=dict(baseline_report.get("signal_evidence", {})),
            )
        else:
            for mode in ("on", "off"):
                feature_name = f"turbo_incremental_{mode}"
                candidate_engine, candidate_raw, summary = apply_turbo_incremental_mode(
                    baseline_engine,
                    baseline_raw,
                    mode=mode,
                )
                candidate_report = evaluate_with_engine(candidate_engine, candidate_raw, dataset_dir).to_dict()
                feature = _feature_summary(
                    feature_name,
                    candidate_report,
                    feature_state={"turbo_incremental": summary},
                )
                case_payload["features"][feature_name] = _attach_outcome(baseline, feature)

    if include_staged_calibration:
        staged_report, _, _, bench_after = run_staged_calibration(
            baseline_engine,
            baseline_raw,
            base_engine_path=base_engine_path,
            dataset_dir=dataset_dir,
            max_evals_per_stage=max_evals_per_stage,
        )
        staged_feature = _staged_feature_payload(staged_report, bench_after)
        case_payload["features"]["staged_after"] = _attach_outcome(baseline, staged_feature)

    return case_payload


def run_validation_batch(
    engine: Engine,
    engine_raw: dict,
    *,
    base_engine_path: Path,
    dataset_dirs: list[Path],
    include_adaptive_toggle: bool,
    include_turbo_toggle: bool,
    include_staged_calibration: bool,
    max_evals_per_stage: int,
) -> dict:
    cases = [
        run_validation_case(
            engine,
            engine_raw,
            base_engine_path=base_engine_path,
            dataset_dir=dataset_dir,
            include_adaptive_toggle=include_adaptive_toggle,
            include_turbo_toggle=include_turbo_toggle,
            include_staged_calibration=include_staged_calibration,
            max_evals_per_stage=max_evals_per_stage,
        )
        for dataset_dir in dataset_dirs
    ]

    feature_summary: dict[str, dict] = {}
    for case in cases:
        for feature_name, payload in case.get("features", {}).items():
            entry = feature_summary.setdefault(
                feature_name,
                {
                    "cases_total": 0,
                    **empty_comparison_outcome_counts(),
                },
            )
            entry["cases_total"] += 1
            outcome = normalize_comparison_outcome(payload.get("outcome", COMPARISON_OUTCOME_DEFAULT))
            if outcome in OUTCOME_ORDER:
                entry[f"{outcome}_cases"] += 1

    payload = {
        "metadata": {
            "base_engine_path": str(base_engine_path),
            "datasets_evaluated": [str(Path(case["dataset"]["path"])) for case in cases],
            "features_requested": {
                "adaptive_toggle": bool(include_adaptive_toggle),
                "turbo_incremental_toggle": bool(include_turbo_toggle),
                "staged_calibration": bool(include_staged_calibration),
            },
        },
        "cases": cases,
        "summary": {"feature_summary": feature_summary},
    }
    return apply_analysis_envelope(
        payload,
        report_type=REPORT_TYPE_VALIDATION_COMPARE,
        context=build_shared_case_context(cases, base_engine_path=base_engine_path),
    )
