from __future__ import annotations

import datetime as dt
from pathlib import Path


REPORT_FAMILY_ANALYSIS = "analysis"
REPORT_FORMAT_VERSION = 1

REPORT_TYPE_COMPARE = "compare_report"
REPORT_TYPE_STAGED_CALIBRATION = "staged_calibration_report"
REPORT_TYPE_VALIDATION_COMPARE = "validation_compare_report"
REPORT_TYPE_AB_COMPARE = "ab_compare_report"
REPORT_TYPE_SENSITIVITY_LOCAL = "sensitivity_local_report"
REPORT_TYPE_OPTIMIZE_GUIDED = "optimize_guided_report"

OBSERVABLE_VE_ACTUAL = "ve_actual"
OBSERVABLE_VE_ACTUAL_SEMANTICS = {
    "available_in_modes": ["v1", "v2"],
    "cross_mode_relation": "comparable_not_identical",
    "v1_meaning": "Modeled VE estimate derived from the 0D intake-flow correlations.",
    "v2_meaning": "Trapped fresh-mass based VE result evaluated at IVC in the coupled solution.",
    "interpretation_note": "Use cross-mode ve_actual comparison for trend and gross plausibility checks, not as a strict parity target.",
}


def _string_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def build_report_context(
    *,
    dataset: dict | None = None,
    dataset_id: object = None,
    engine_id: object = None,
    preset_path: object = None,
    engine_path: object = None,
    base_engine_path: object = None,
) -> dict:
    context: dict[str, str] = {}
    dataset = dict(dataset or {})
    merged_values = {
        "dataset_id": dataset.get("dataset_id"),
        "engine_id": dataset.get("engine_id"),
        "preset_path": dataset.get("preset_path"),
        "engine_path": engine_path,
        "base_engine_path": base_engine_path,
    }
    if dataset_id is not None:
        merged_values["dataset_id"] = dataset_id
    if engine_id is not None:
        merged_values["engine_id"] = engine_id
    if preset_path is not None:
        merged_values["preset_path"] = preset_path
    for key, value in merged_values.items():
        text = _string_value(value)
        if text is not None:
            context[key] = text
    return context


def build_shared_case_context(cases: list[dict], *, base_engine_path: object = None) -> dict:
    if not cases:
        return build_report_context(base_engine_path=base_engine_path)
    shared: dict[str, str] = {}
    for key in ("dataset_id", "engine_id", "preset_path"):
        values = {
            str(case.get("dataset", {}).get(key))
            for case in cases
            if isinstance(case, dict)
            and isinstance(case.get("dataset"), dict)
            and case["dataset"].get(key) not in {None, ""}
        }
        if len(values) == 1:
            shared[key] = next(iter(values))
    return build_report_context(
        dataset_id=shared.get("dataset_id"),
        engine_id=shared.get("engine_id"),
        preset_path=shared.get("preset_path"),
        base_engine_path=base_engine_path,
    )


def dataset_context_from_dir(dataset_dir: Path) -> dict:
    metadata_path = dataset_dir / "metadata.json"
    if not metadata_path.exists():
        return {}
    import json

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return build_report_context(dataset=metadata)


def resolve_generated_at_utc(payload: dict, explicit: str | None = None) -> str:
    if explicit:
        return str(explicit)
    existing = payload.get("generated_at_utc")
    if existing:
        return str(existing)
    metadata = payload.get("metadata")
    if isinstance(metadata, dict) and metadata.get("timestamp"):
        return str(metadata["timestamp"])
    return dt.datetime.utcnow().isoformat() + "Z"


def apply_analysis_envelope(
    payload: dict,
    *,
    report_type: str,
    context: dict | None = None,
    generated_at_utc: str | None = None,
) -> dict:
    merged_context: dict[str, str] = {}
    existing_context = payload.get("context")
    if isinstance(existing_context, dict):
        for key, value in existing_context.items():
            text = _string_value(value)
            if text is not None:
                merged_context[str(key)] = text
    if context:
        for key, value in context.items():
            text = _string_value(value)
            if text is not None:
                merged_context[str(key)] = text

    payload["report_type"] = str(report_type)
    payload["report_format_version"] = REPORT_FORMAT_VERSION
    payload["report_family"] = REPORT_FAMILY_ANALYSIS
    payload["generated_at_utc"] = resolve_generated_at_utc(payload, explicit=generated_at_utc)
    if merged_context:
        payload["context"] = merged_context
    return payload


def build_observable_semantics(*observable_names: str) -> dict:
    semantics: dict[str, dict] = {}
    for name in observable_names:
        normalized = str(name).strip()
        if normalized == OBSERVABLE_VE_ACTUAL:
            semantics[normalized] = dict(OBSERVABLE_VE_ACTUAL_SEMANTICS)
    return semantics


def apply_observable_semantics(payload: dict, *observable_names: str) -> dict:
    merged: dict[str, dict] = {}
    existing = payload.get("observable_semantics")
    if isinstance(existing, dict):
        for key, value in existing.items():
            if isinstance(value, dict):
                merged[str(key)] = dict(value)
    for key, value in build_observable_semantics(*observable_names).items():
        merged[key] = value
    if merged:
        payload["observable_semantics"] = merged
    return payload
