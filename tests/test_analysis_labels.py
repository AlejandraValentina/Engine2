from __future__ import annotations

from pywavedyn.analysis_labels import (
    COMPARISON_OUTCOMES,
    ROBUSTNESS_LEVELS,
    comparison_outcome_label,
    empty_comparison_outcome_counts,
    normalize_comparison_outcome,
    robustness_level,
    stage_status_from_entry,
)


def test_comparison_outcome_helpers_keep_official_vocabulary() -> None:
    assert COMPARISON_OUTCOMES == (
        "improved",
        "partial_improvement",
        "tradeoff",
        "no_clear_benefit",
        "no_conclusion",
    )
    assert normalize_comparison_outcome("tradeoff") == "tradeoff"
    assert normalize_comparison_outcome("unexpected") == "no_conclusion"
    assert comparison_outcome_label("no_clear_benefit") == "no clear benefit"
    assert comparison_outcome_label("unexpected") == "no conclusion"
    assert empty_comparison_outcome_counts() == {
        "improved_cases": 0,
        "partial_improvement_cases": 0,
        "tradeoff_cases": 0,
        "no_clear_benefit_cases": 0,
        "no_conclusion_cases": 0,
    }


def test_stage_status_from_entry_prefers_omitted_then_acceptance() -> None:
    assert stage_status_from_entry({"accepted": True, "notes": "Stage omitted because signals are missing."}) == "omitted"
    assert stage_status_from_entry({"accepted": True, "notes": "Candidate accepted."}) == "accepted"
    assert stage_status_from_entry({"accepted": False, "notes": "Candidate was rejected."}) == "rejected"


def test_robustness_level_thresholds_match_official_labels() -> None:
    assert ROBUSTNESS_LEVELS == (
        "low_sensitivity",
        "moderate_sensitivity",
        "high_sensitivity",
    )
    assert robustness_level(0.005) == "low_sensitivity"
    assert robustness_level(0.02) == "moderate_sensitivity"
    assert robustness_level(0.08) == "high_sensitivity"
