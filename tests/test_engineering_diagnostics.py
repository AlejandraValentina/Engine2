from __future__ import annotations

from core.engine_components import Engine
from pywavedyn.engineering_diagnostics import (
    diagnose_compare_report,
    diagnose_dyno_output,
    diagnose_staged_calibration_report,
)


def test_compare_diagnostics_emit_airflow_shortfall_when_map_and_power_are_biased_low() -> None:
    report = {
        "points": [
            {
                "rpm": 3000.0,
                "target": {"torque_nm": 200.0, "power_hp": 100.0, "map_kpa": 100.0},
                "predicted": {"torque_nm": 160.0, "power_hp": 80.0, "map_kpa": 90.0},
            },
            {
                "rpm": 5000.0,
                "target": {"torque_nm": 210.0, "power_hp": 150.0, "map_kpa": 102.0},
                "predicted": {"torque_nm": 165.0, "power_hp": 120.0, "map_kpa": 92.0},
            },
        ],
        "errors": {
            "torque_nm": {"mape": 0.2},
            "power_hp": {"mape": 0.2},
            "total_mape": 0.2,
            "optional_signals": {"map_kpa": {"mape": 0.09, "count": 2}},
        },
        "contract": {"torque_mape_max": 0.1, "power_mape_max": 0.1, "pass": False},
        "signal_coverage": {
            "dataset_signals": ["torque_nm", "power_hp", "map_kpa"],
            "compared_signals": ["torque_nm", "power_hp", "map_kpa"],
            "skipped_signals": [],
        },
    }

    diagnostics = diagnose_compare_report(report)
    ids = {diag["id"] for diag in diagnostics}
    assert "possible_airflow_shortfall" in ids
    assert "compare_contract_fail" in ids


def test_compare_diagnostics_do_not_emit_unsupported_boost_claim_without_boost_signal() -> None:
    report = {
        "points": [
            {"rpm": 3000.0, "target": {"torque_nm": 100.0, "power_hp": 50.0}, "predicted": {"torque_nm": 100.0, "power_hp": 50.0}}
        ],
        "errors": {"torque_nm": {"mape": 0.0}, "power_hp": {"mape": 0.0}, "total_mape": 0.0},
        "contract": {"torque_mape_max": 0.1, "power_mape_max": 0.1, "pass": True},
        "signal_coverage": {
            "dataset_signals": ["torque_nm", "power_hp"],
            "compared_signals": ["torque_nm", "power_hp"],
            "skipped_signals": [],
        },
    }

    diagnostics = diagnose_compare_report(report)
    assert all(diag["id"] not in {"boost_underprediction", "boost_overprediction"} for diag in diagnostics)


def test_staged_diagnostics_emit_omitted_and_partial_improvement() -> None:
    report = {
        "stages": [
            {
                "stage_name": "combustion_adaptive",
                "params_touched": ["adaptive_duration_scale", "adaptive_ca50_offset_deg"],
                "signals_used": [],
                "before_metrics": {"total_mape": 0.22},
                "after_metrics": {"total_mape": 0.22},
                "accepted": False,
                "notes": "Stage omitted because combustion.adaptive_model.enabled is false.",
            }
        ]
    }
    bench_before = {"errors": {"total_mape": 0.22}, "contract": {"pass": False}}
    bench_after = {"errors": {"total_mape": 0.18}, "contract": {"pass": False}}

    diagnostics = diagnose_staged_calibration_report(report, bench_before=bench_before, bench_after=bench_after)
    ids = {diag["id"] for diag in diagnostics}
    assert "combustion_adaptive_omitted" in ids
    assert "adaptive_combustion_disabled" in ids
    assert "staged_partial_improvement" in ids


def test_staged_diagnostics_emit_turbo_stage_helped_when_stage_is_accepted() -> None:
    report = {
        "stages": [
            {
                "stage_name": "turbo",
                "params_touched": ["turbo_target_boost_scale", "turbo_spool_rpm_offset"],
                "signals_used": ["boost_kpa", "power_hp"],
                "before_metrics": {"total_mape": 0.20},
                "after_metrics": {"total_mape": 0.10},
                "accepted": True,
                "notes": "Turbo stage accepted.",
            }
        ]
    }

    diagnostics = diagnose_staged_calibration_report(report)
    assert any(diag["id"] == "turbo_stage_helped" for diag in diagnostics)


def test_dyno_diagnostics_emit_knock_and_low_boost_when_supported() -> None:
    engine = Engine()
    engine.turbo.enabled = True
    engine.turbo.target_boost_kpa = 100.0
    payload = {
        "results": [
            {"rpm": 2000.0, "boost_kpa": 10.0, "knock_penalty_pct": 0.0, "knock_warning": False},
            {"rpm": 4000.0, "boost_kpa": 40.0, "knock_penalty_pct": 3.0, "knock_warning": True},
            {"rpm": 6500.0, "boost_kpa": 60.0, "knock_penalty_pct": 0.0, "knock_warning": False},
        ]
    }

    diagnostics = diagnose_dyno_output(payload, engine=engine)
    ids = {diag["id"] for diag in diagnostics}
    assert "knock_penalty_active" in ids
    assert "boost_below_configured_target" in ids
