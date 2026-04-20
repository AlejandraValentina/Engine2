from __future__ import annotations

from pywavedyn.analysis_contract import (
    OBSERVABLE_VE_ACTUAL,
    REPORT_FAMILY_ANALYSIS,
    REPORT_FORMAT_VERSION,
    REPORT_TYPE_COMPARE,
    apply_analysis_envelope,
    apply_observable_semantics,
    build_report_context,
    build_shared_case_context,
)


def test_apply_analysis_envelope_uses_metadata_timestamp_and_merges_context() -> None:
    payload = {
        "metadata": {"timestamp": "2026-04-08T12:00:00Z"},
        "context": {"dataset_id": "existing_dataset"},
    }

    apply_analysis_envelope(
        payload,
        report_type=REPORT_TYPE_COMPARE,
        context=build_report_context(engine_id="k20", preset_path="presets/honda_k20.json"),
    )

    assert payload["report_type"] == REPORT_TYPE_COMPARE
    assert payload["report_format_version"] == REPORT_FORMAT_VERSION
    assert payload["report_family"] == REPORT_FAMILY_ANALYSIS
    assert payload["generated_at_utc"] == "2026-04-08T12:00:00Z"
    assert payload["context"] == {
        "dataset_id": "existing_dataset",
        "engine_id": "k20",
        "preset_path": "presets/honda_k20.json",
    }


def test_build_shared_case_context_only_promotes_shared_dataset_fields() -> None:
    cases = [
        {"dataset": {"dataset_id": "case_a", "engine_id": "k20", "preset_path": "presets/honda_k20.json"}},
        {"dataset": {"dataset_id": "case_b", "engine_id": "k20", "preset_path": "presets/honda_k20.json"}},
    ]

    context = build_shared_case_context(cases, base_engine_path="presets/honda_k20.json")

    assert context == {
        "engine_id": "k20",
        "preset_path": "presets/honda_k20.json",
        "base_engine_path": "presets/honda_k20.json",
    }


def test_apply_observable_semantics_adds_official_ve_actual_note() -> None:
    payload = {}

    apply_observable_semantics(payload, OBSERVABLE_VE_ACTUAL)

    ve_actual = payload["observable_semantics"]["ve_actual"]
    assert ve_actual["available_in_modes"] == ["v1", "v2"]
    assert ve_actual["cross_mode_relation"] == "comparable_not_identical"
    assert "modeled ve estimate" in ve_actual["v1_meaning"].lower()
    assert "trapped fresh-mass" in ve_actual["v2_meaning"].lower()
