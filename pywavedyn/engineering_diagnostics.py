from __future__ import annotations

from statistics import mean
from typing import Any

from core.engine_components import Engine
from pywavedyn.analysis_labels import stage_status_from_entry


def _diagnostic(
    *,
    diag_id: str,
    title: str,
    severity: str,
    confidence: str,
    signals_used: list[str],
    metrics_used: dict[str, Any],
    rationale: str,
    suggested_interpretation: str,
) -> dict:
    return {
        "id": diag_id,
        "title": title,
        "severity": severity,
        "confidence": confidence,
        "signals_used": signals_used,
        "metrics_used": metrics_used,
        "rationale": rationale,
        "suggested_interpretation": suggested_interpretation,
    }


def _relative_biases(report: dict, signal: str) -> list[float]:
    values: list[float] = []
    for point in report.get("points", []):
        target = point.get("target", {}).get(signal)
        predicted = point.get("predicted", {}).get(signal)
        if target is None or predicted is None:
            continue
        denom = max(abs(float(target)), 1e-9)
        values.append((float(predicted) - float(target)) / denom)
    return values


def diagnose_compare_report(report: dict) -> list[dict]:
    diagnostics: list[dict] = []
    contract = report.get("contract", {})
    coverage = report.get("signal_coverage", {})
    errors = report.get("errors", {})
    skipped_signals = list(coverage.get("skipped_signals", []))

    if not bool(contract.get("pass", True)):
        diagnostics.append(
            _diagnostic(
                diag_id="compare_contract_fail",
                title="Base torque/power contract failed",
                severity="warning",
                confidence="high",
                signals_used=["torque_nm", "power_hp"],
                metrics_used={
                    "torque_mape": float(errors.get("torque_nm", {}).get("mape", 0.0)),
                    "power_mape": float(errors.get("power_hp", {}).get("mape", 0.0)),
                    "contract_limits": {
                        "torque_mape_max": float(contract.get("torque_mape_max", 0.0)),
                        "power_mape_max": float(contract.get("power_mape_max", 0.0)),
                    },
                },
                rationale="The current torque/power comparison exceeded the benchmark contract limits.",
                suggested_interpretation="Treat the current setup as mismatched to the imported dyno data until the main torque/power error is reduced.",
            )
        )

    if skipped_signals:
        diagnostics.append(
            _diagnostic(
                diag_id="compare_skipped_signals",
                title="Some dataset signals could not be scored",
                severity="info",
                confidence="high",
                signals_used=skipped_signals,
                metrics_used={"skipped_signals": skipped_signals},
                rationale="The dataset includes optional channels that the current simulator path does not currently predict.",
                suggested_interpretation="Do not over-interpret the fit for the skipped channels; only the compared signals contributed to the scored error.",
            )
        )

    torque_bias = _relative_biases(report, "torque_nm")
    power_bias = _relative_biases(report, "power_hp")
    map_bias = _relative_biases(report, "map_kpa")
    boost_bias = _relative_biases(report, "boost_kpa")
    lambda_bias = _relative_biases(report, "lambda")
    afr_bias = _relative_biases(report, "afr")

    if map_bias and torque_bias and power_bias:
        mean_map_bias = mean(map_bias)
        mean_torque_bias = mean(torque_bias)
        mean_power_bias = mean(power_bias)
        if mean_map_bias <= -0.05 and mean_torque_bias <= -0.08 and mean_power_bias <= -0.08:
            diagnostics.append(
                _diagnostic(
                    diag_id="possible_airflow_shortfall",
                    title="Possible airflow shortfall or intake-side restriction",
                    severity="warning",
                    confidence="medium",
                    signals_used=["map_kpa", "torque_nm", "power_hp"],
                    metrics_used={
                        "map_bias_mean": float(mean_map_bias),
                        "torque_bias_mean": float(mean_torque_bias),
                        "power_bias_mean": float(mean_power_bias),
                    },
                    rationale="Simulated MAP is below the measured MAP while simulated torque and power are also biased low.",
                    suggested_interpretation="This points to a possible airflow / VE shortfall in the current setup. Check intake-side tuning, VE scaling, and runner assumptions before claiming a hardware restriction.",
                )
            )

    if boost_bias:
        mean_boost_bias = mean(boost_bias)
        if mean_boost_bias <= -0.15:
            diagnostics.append(
                _diagnostic(
                    diag_id="boost_underprediction",
                    title="Boost appears insufficient relative to the dataset",
                    severity="warning",
                    confidence="medium",
                    signals_used=["boost_kpa"],
                    metrics_used={"boost_bias_mean": float(mean_boost_bias)},
                    rationale="The simulated boost channel is materially below the measured boost channel across the compared points.",
                    suggested_interpretation="Possible insufficient or late boost behavior in the current model setup. Review turbo sizing, wastegate behavior, and target boost assumptions.",
                )
            )
        elif mean_boost_bias >= 0.15:
            diagnostics.append(
                _diagnostic(
                    diag_id="boost_overprediction",
                    title="Boost appears overpredicted relative to the dataset",
                    severity="warning",
                    confidence="medium",
                    signals_used=["boost_kpa"],
                    metrics_used={"boost_bias_mean": float(mean_boost_bias)},
                    rationale="The simulated boost channel is materially above the measured boost channel across the compared points.",
                    suggested_interpretation="Review compressor ratio targets, wastegate behavior, and manifold-pressure assumptions before using this fit as representative.",
                )
            )
        low_rpm_biases = []
        high_rpm_biases = []
        points = [point for point in report.get("points", []) if point.get("target", {}).get("boost_kpa") is not None and point.get("predicted", {}).get("boost_kpa") is not None]
        if len(points) >= 4:
            sorted_points = sorted(points, key=lambda point: float(point["rpm"]))
            split = max(len(sorted_points) // 2, 1)
            for point in sorted_points[:split]:
                target = float(point["target"]["boost_kpa"])
                pred = float(point["predicted"]["boost_kpa"])
                low_rpm_biases.append((pred - target) / max(abs(target), 1e-9))
            for point in sorted_points[split:]:
                target = float(point["target"]["boost_kpa"])
                pred = float(point["predicted"]["boost_kpa"])
                high_rpm_biases.append((pred - target) / max(abs(target), 1e-9))
            if low_rpm_biases and high_rpm_biases and mean(low_rpm_biases) < -0.15 and mean(high_rpm_biases) > mean(low_rpm_biases) + 0.1:
                diagnostics.append(
                    _diagnostic(
                        diag_id="possible_late_spool",
                        title="Possible late boost build relative to the measured curve",
                        severity="info",
                        confidence="medium",
                        signals_used=["boost_kpa"],
                        metrics_used={
                            "low_rpm_boost_bias_mean": float(mean(low_rpm_biases)),
                            "high_rpm_boost_bias_mean": float(mean(high_rpm_biases)),
                        },
                        rationale="Boost underprediction is materially stronger in the lower-RPM portion of the compared band than in the upper portion.",
                        suggested_interpretation="This suggests boost build timing later than the measured curve. Review spool-related settings before concluding the turbo hardware itself is wrong.",
                    )
                )

    if lambda_bias:
        mean_lambda_bias = mean(lambda_bias)
        if abs(mean_lambda_bias) >= 0.05:
            direction = "leaner" if mean_lambda_bias > 0.0 else "richer"
            diagnostics.append(
                _diagnostic(
                    diag_id="lambda_mismatch",
                    title="Lambda mismatch against measured data",
                    severity="warning",
                    confidence="medium",
                    signals_used=["lambda"],
                    metrics_used={"lambda_bias_mean": float(mean_lambda_bias)},
                    rationale="The simulated lambda channel is consistently offset from the measured lambda channel.",
                    suggested_interpretation=f"The current setup is trending {direction} than the dataset. Review fueling assumptions and sensor/stoich conventions before treating combustion conclusions as final.",
                )
            )
    elif afr_bias:
        mean_afr_bias = mean(afr_bias)
        if abs(mean_afr_bias) >= 0.05:
            direction = "leaner" if mean_afr_bias > 0.0 else "richer"
            diagnostics.append(
                _diagnostic(
                    diag_id="afr_mismatch",
                    title="AFR mismatch against measured data",
                    severity="warning",
                    confidence="medium",
                    signals_used=["afr"],
                    metrics_used={"afr_bias_mean": float(mean_afr_bias)},
                    rationale="The simulated AFR channel is consistently offset from the measured AFR channel.",
                    suggested_interpretation=f"The current setup is trending {direction} than the dataset. Review fueling assumptions and AFR/lambda conventions before using the result to tune combustion.",
                )
            )

    return diagnostics


def diagnose_staged_calibration_report(report: dict, *, bench_before: dict | None = None, bench_after: dict | None = None) -> list[dict]:
    diagnostics: list[dict] = []
    stages = list(report.get("stages", []))

    for stage in stages:
        stage_name = str(stage.get("stage_name", "unknown"))
        notes = str(stage.get("notes", ""))
        notes_l = notes.lower()
        status = stage_status_from_entry(stage)
        params_touched = list(stage.get("params_touched", []))
        signals_used = list(stage.get("signals_used", []))
        before_total = float(stage.get("before_metrics", {}).get("total_mape", 0.0))
        after_total = float(stage.get("after_metrics", {}).get("total_mape", before_total))

        if status == "omitted":
            diagnostics.append(
                _diagnostic(
                    diag_id=f"{stage_name}_omitted",
                    title=f"Stage '{stage_name}' was omitted",
                    severity="info",
                    confidence="high",
                    signals_used=signals_used,
                    metrics_used={"before_total_mape": before_total, "after_total_mape": after_total},
                    rationale=notes,
                    suggested_interpretation="This stage was intentionally skipped because the current backend, engine setup, or dataset does not provide enough support to run it safely.",
                )
            )
        elif status == "rejected":
            diagnostics.append(
                _diagnostic(
                    diag_id=f"{stage_name}_rejected",
                    title=f"Stage '{stage_name}' did not improve the filtered objective",
                    severity="info",
                    confidence="high",
                    signals_used=signals_used,
                    metrics_used={"before_total_mape": before_total, "after_total_mape": after_total},
                    rationale=notes or "The candidate stage run did not reduce the filtered objective enough to be accepted.",
                    suggested_interpretation="Keep the previous calibration state for this stage; the available evidence did not support applying the candidate change.",
                )
            )

    if bench_before is not None and bench_after is not None:
        before_total = float(bench_before.get("errors", {}).get("total_mape", 0.0))
        after_total = float(bench_after.get("errors", {}).get("total_mape", before_total))
        before_pass = bool(bench_before.get("contract", {}).get("pass", False))
        after_pass = bool(bench_after.get("contract", {}).get("pass", False))
        delta = before_total - after_total

        if delta > 1e-6 and not after_pass:
            diagnostics.append(
                _diagnostic(
                    diag_id="staged_partial_improvement",
                    title="Calibration improved error only partially",
                    severity="warning",
                    confidence="high",
                    signals_used=["torque_nm", "power_hp"],
                    metrics_used={"before_total_mape": before_total, "after_total_mape": after_total, "delta_total_mape": delta},
                    rationale="The staged calibration reduced total MAPE, but the final torque/power contract still fails.",
                    suggested_interpretation="The current staged knobs helped, but they were not enough to fully match the dataset. Treat this as progress, not as final agreement.",
                )
            )
        elif delta <= 1e-6:
            diagnostics.append(
                _diagnostic(
                    diag_id="staged_no_material_improvement",
                    title="Staged calibration did not materially improve the final error",
                    severity="info",
                    confidence="high",
                    signals_used=["torque_nm", "power_hp"],
                    metrics_used={"before_total_mape": before_total, "after_total_mape": after_total},
                    rationale="The overall benchmark error after staged calibration is effectively unchanged.",
                    suggested_interpretation="The current exposed stages were not sufficient to improve the fit materially for this dataset.",
                )
            )
        if not before_pass and after_pass:
            diagnostics.append(
                _diagnostic(
                    diag_id="staged_contract_recovered",
                    title="Staged calibration recovered the benchmark contract",
                    severity="info",
                    confidence="high",
                    signals_used=["torque_nm", "power_hp"],
                    metrics_used={"before_total_mape": before_total, "after_total_mape": after_total},
                    rationale="The calibrated engine moved from contract fail to contract pass.",
                    suggested_interpretation="This is a materially useful calibration improvement for the current dataset and exposed parameters.",
                )
            )

    adaptive_stage = next((stage for stage in stages if stage.get("stage_name") == "combustion_adaptive"), None)
    if adaptive_stage is not None:
        notes_l = str(adaptive_stage.get("notes", "")).lower()
        if bool(adaptive_stage.get("accepted", False)):
            diagnostics.append(
                _diagnostic(
                    diag_id="adaptive_combustion_helped",
                    title="Adaptive combustion improved the staged fit",
                    severity="info",
                    confidence="high",
                    signals_used=list(adaptive_stage.get("signals_used", [])),
                    metrics_used={
                        "before_total_mape": float(adaptive_stage.get("before_metrics", {}).get("total_mape", 0.0)),
                        "after_total_mape": float(adaptive_stage.get("after_metrics", {}).get("total_mape", 0.0)),
                    },
                    rationale="The dedicated adaptive-combustion stage was accepted by the staged calibration flow.",
                    suggested_interpretation="The global adaptive combustion schedule contributed useful error reduction for this dataset.",
                )
            )
        elif "enabled is false" in notes_l:
            diagnostics.append(
                _diagnostic(
                    diag_id="adaptive_combustion_disabled",
                    title="Adaptive combustion stage omitted because the mode is disabled",
                    severity="info",
                    confidence="high",
                    signals_used=[],
                    metrics_used={},
                    rationale=adaptive_stage.get("notes", ""),
                    suggested_interpretation="No adaptive-combustion conclusion should be drawn from this calibration run because the mode was not active.",
                )
            )

    turbo_stage = next((stage for stage in stages if stage.get("stage_name") == "turbo"), None)
    if turbo_stage is not None and bool(turbo_stage.get("accepted", False)):
        diagnostics.append(
            _diagnostic(
                diag_id="turbo_stage_helped",
                title="Turbo stage improved the staged fit",
                severity="info",
                confidence="high",
                signals_used=list(turbo_stage.get("signals_used", [])),
                metrics_used={
                    "before_total_mape": float(turbo_stage.get("before_metrics", {}).get("total_mape", 0.0)),
                    "after_total_mape": float(turbo_stage.get("after_metrics", {}).get("total_mape", 0.0)),
                },
                rationale="The turbo stage was accepted by the staged calibration flow.",
                suggested_interpretation="The exposed turbo controls contributed useful error reduction for the current dataset and engine setup.",
            )
        )

    return diagnostics


def diagnose_dyno_output(payload: dict, *, engine: Engine | None = None) -> list[dict]:
    diagnostics: list[dict] = []
    results = list(payload.get("results", []))
    if not results:
        return diagnostics

    knock_penalties = [float(entry.get("knock_penalty_pct", 0.0)) for entry in results if float(entry.get("knock_penalty_pct", 0.0)) > 0.0]
    knock_rpms = [float(entry.get("rpm", 0.0)) for entry in results if bool(entry.get("knock_warning")) or float(entry.get("knock_penalty_pct", 0.0)) > 0.0]
    if knock_penalties:
        diagnostics.append(
            _diagnostic(
                diag_id="knock_penalty_active",
                title="Knock penalty is active in the dyno sweep",
                severity="warning",
                confidence="high",
                signals_used=["knock_penalty_pct"],
                metrics_used={"max_knock_penalty_pct": max(knock_penalties), "rpm_points": knock_rpms},
                rationale="The dyno run includes one or more RPM points with non-zero knock penalty.",
                suggested_interpretation="The current spark/combustion setup is knock-limited at the flagged RPM points; treat the affected power as penalized rather than clean MBT output.",
            )
        )

    boost_entries = [(float(entry.get("rpm", 0.0)), float(entry.get("boost_kpa", 0.0))) for entry in results if "boost_kpa" in entry]
    if boost_entries:
        max_boost = max(boost for _, boost in boost_entries)
        rpm_min = min(rpm for rpm, _ in boost_entries)
        rpm_max = max(rpm for rpm, _ in boost_entries)
        if max_boost >= 20.0:
            threshold = 0.9 * max_boost
            first_near_peak = min(rpm for rpm, boost in boost_entries if boost >= threshold)
            if rpm_max > rpm_min and first_near_peak >= rpm_min + 0.7 * (rpm_max - rpm_min):
                diagnostics.append(
                    _diagnostic(
                        diag_id="boost_build_late_relative_to_peak",
                        title="Boost builds late relative to its observed peak",
                        severity="info",
                        confidence="medium",
                        signals_used=["boost_kpa"],
                        metrics_used={"peak_boost_kpa": max_boost, "first_90pct_peak_rpm": first_near_peak},
                        rationale="The dyno sweep reaches 90% of observed peak boost only near the upper end of the RPM band.",
                        suggested_interpretation="This suggests late boost buildup relative to the measured operating band, not necessarily an outright turbo fault.",
                    )
                )

        if engine is not None and bool(getattr(engine.turbo, "enabled", False)):
            target_boost = getattr(engine.turbo, "target_boost_kpa", None)
            if target_boost is not None and float(target_boost) > 0.0 and max_boost < 0.8 * float(target_boost):
                diagnostics.append(
                    _diagnostic(
                        diag_id="boost_below_configured_target",
                        title="Observed boost stays below the configured target",
                        severity="warning",
                        confidence="medium",
                        signals_used=["boost_kpa"],
                        metrics_used={"peak_boost_kpa": max_boost, "target_boost_kpa": float(target_boost)},
                        rationale="Peak boost in the dyno sweep stays materially below the configured target boost.",
                        suggested_interpretation="Possible insufficient boost or conservative turbo/wastegate behavior relative to the configured target. Verify the target and turbo assumptions before using the run for final tuning.",
                    )
                )

    return diagnostics
