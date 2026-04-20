from __future__ import annotations

from collections.abc import Iterable


CONTRACT_BASELINE_GROUP = "contract_baseline"
TURBO_GROUP = "turbo"
FUELING_GROUP = "fueling"
THERMAL_GROUP = "thermal"

SIGNAL_GROUPS: dict[str, tuple[str, ...]] = {
    CONTRACT_BASELINE_GROUP: ("torque_nm", "power_hp"),
    TURBO_GROUP: ("boost_kpa", "map_kpa"),
    FUELING_GROUP: ("lambda", "afr"),
    THERMAL_GROUP: ("egt_c",),
}

GROUP_LABELS: dict[str, str] = {
    CONTRACT_BASELINE_GROUP: "torque/power baseline",
    TURBO_GROUP: "turbo",
    FUELING_GROUP: "fueling",
    THERMAL_GROUP: "thermal",
}


def _normalize_signals(values: Iterable[object] | None) -> list[str]:
    if values is None:
        return []
    normalized = {str(value) for value in values if str(value)}
    return sorted(normalized)


def _group_note(group_name: str, *, present: list[str], compared: list[str], skipped: list[str], report_mode: bool) -> str:
    label = GROUP_LABELS[group_name]
    if group_name == CONTRACT_BASELINE_GROUP:
        if compared:
            return "Torque/power contract signals were available and scored in this report."
        if present:
            return "Dataset carries the torque/power baseline used by compare and calibration."
        return "Dataset is missing the normal torque/power baseline."

    if compared:
        joined = ", ".join(compared)
        return f"{label.capitalize()} evidence is available and currently compared on: {joined}."
    if present:
        joined_present = ", ".join(present)
        if report_mode:
            if skipped:
                joined_skipped = ", ".join(skipped)
                return (
                    f"{label.capitalize()} channels are present in the dataset ({joined_present}) "
                    f"but not fully scoreable in this report; skipped: {joined_skipped}."
                )
            return f"{label.capitalize()} channels are present in the dataset ({joined_present}) but were not compared in this report."
        return f"Dataset carries {label} channels: {joined_present}."

    if group_name == TURBO_GROUP:
        return "No committed turbo evidence (`boost_kpa`/`map_kpa`) is available in this dataset."
    if group_name == FUELING_GROUP:
        return "No committed fueling evidence (`lambda`/`afr`) is available in this dataset."
    return "No committed thermal evidence (`egt_c`) is available in this dataset."


def build_signal_evidence(
    *,
    dataset_signals: Iterable[object] | None,
    compared_signals: Iterable[object] | None = None,
    skipped_signals: Iterable[object] | None = None,
) -> dict:
    dataset = _normalize_signals(dataset_signals)
    compared = _normalize_signals(compared_signals)
    skipped = _normalize_signals(skipped_signals)
    dataset_set = set(dataset)
    compared_set = set(compared)
    skipped_set = set(skipped)
    report_mode = compared_signals is not None or skipped_signals is not None

    groups: dict[str, dict] = {}
    limitations: list[str] = []
    for group_name, group_signals in SIGNAL_GROUPS.items():
        present = [signal for signal in group_signals if signal in dataset_set]
        compared_in_group = [signal for signal in group_signals if signal in compared_set]
        skipped_in_group = [signal for signal in group_signals if signal in skipped_set]

        if compared_in_group:
            status = "compared"
        elif present:
            status = "present_not_compared" if report_mode else "available"
        else:
            status = "not_available"

        note = _group_note(
            group_name,
            present=present,
            compared=compared_in_group,
            skipped=skipped_in_group,
            report_mode=report_mode,
        )
        groups[group_name] = {
            "group_label": GROUP_LABELS[group_name],
            "signals_present": present,
            "signals_compared": compared_in_group,
            "signals_skipped": skipped_in_group,
            "status": status,
            "note": note,
        }
        if group_name != CONTRACT_BASELINE_GROUP and status != "compared":
            limitations.append(note)

    return {
        "dataset_signals": dataset,
        "compared_signals": compared,
        "skipped_signals": skipped,
        "groups": groups,
        "limitations": limitations,
    }
