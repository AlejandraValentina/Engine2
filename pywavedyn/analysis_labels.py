from __future__ import annotations

from collections.abc import Mapping


COMPARISON_OUTCOMES = (
    "improved",
    "partial_improvement",
    "tradeoff",
    "no_clear_benefit",
    "no_conclusion",
)
COMPARISON_OUTCOME_DEFAULT = "no_conclusion"
COMPARISON_OUTCOME_LABELS = {
    "improved": "improved",
    "partial_improvement": "partial_improvement",
    "tradeoff": "tradeoff",
    "no_clear_benefit": "no clear benefit",
    "no_conclusion": "no conclusion",
}

STAGE_STATUSES = (
    "accepted",
    "rejected",
    "omitted",
)
STAGE_STATUS_LABELS = {
    "accepted": "accepted",
    "rejected": "rejected",
    "omitted": "omitted",
}

ROBUSTNESS_LEVELS = (
    "low_sensitivity",
    "moderate_sensitivity",
    "high_sensitivity",
)


def normalize_comparison_outcome(value: object) -> str:
    normalized = str(value or COMPARISON_OUTCOME_DEFAULT)
    if normalized in COMPARISON_OUTCOMES:
        return normalized
    return COMPARISON_OUTCOME_DEFAULT


def comparison_outcome_label(value: object) -> str:
    return COMPARISON_OUTCOME_LABELS[normalize_comparison_outcome(value)]


def empty_comparison_outcome_counts() -> dict[str, int]:
    return {f"{outcome}_cases": 0 for outcome in COMPARISON_OUTCOMES}


def stage_status_from_entry(stage: Mapping[str, object]) -> str:
    notes = str(stage.get("notes", "")).lower()
    if "omitted" in notes:
        return "omitted"
    return "accepted" if bool(stage.get("accepted", False)) else "rejected"


def stage_status_label(value: object) -> str:
    normalized = str(value or "rejected")
    if normalized not in STAGE_STATUS_LABELS:
        normalized = "rejected"
    return STAGE_STATUS_LABELS[normalized]


def robustness_level(max_abs_delta: float) -> str:
    if max_abs_delta < 0.01:
        return "low_sensitivity"
    if max_abs_delta < 0.05:
        return "moderate_sensitivity"
    return "high_sensitivity"
