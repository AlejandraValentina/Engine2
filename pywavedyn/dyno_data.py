from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from pathlib import Path

from pywavedyn.analysis_evidence import build_signal_evidence


CANONICAL_SIGNAL_UNITS = {
    "rpm": "rpm",
    "torque_nm": "N*m",
    "power_hp": "hp",
    "boost_kpa": "kPa_gauge",
    "map_kpa": "kPa_abs",
    "lambda": "lambda",
    "afr": "afr_mass",
    "egt_c": "degC",
}

OPTIONAL_SIGNALS = {"boost_kpa", "map_kpa", "lambda", "afr", "egt_c"}
CORE_SIGNALS = {"rpm", "torque_nm", "power_hp"}
ALL_SIGNALS = CORE_SIGNALS | OPTIONAL_SIGNALS

_LBFT_TO_NM = 1.3558179483
_KW_TO_HP = 1.34102209
_PSI_TO_KPA = 6.894757293168361


def parse_mapping_text(text: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not text.strip():
        return mapping
    for part in text.split(","):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError("mapping entries must be formatted as canonical=source_field")
        key, value = item.split("=", 1)
        canonical = key.strip()
        source_field = value.strip()
        if canonical not in ALL_SIGNALS:
            raise ValueError(f"Unknown canonical signal '{canonical}' in mapping")
        if not source_field:
            raise ValueError(f"Missing source field for mapping '{canonical}'")
        mapping[canonical] = source_field
    return mapping


def parse_units_text(text: str) -> dict[str, str]:
    units: dict[str, str] = {}
    if not text.strip():
        return units
    for part in text.split(","):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError("unit entries must be formatted as canonical=unit")
        key, value = item.split("=", 1)
        canonical = key.strip()
        unit = value.strip()
        if canonical not in ALL_SIGNALS:
            raise ValueError(f"Unknown canonical signal '{canonical}' in units")
        if not unit:
            raise ValueError(f"Missing unit for '{canonical}'")
        units[canonical] = unit
    return units


def _infer_source_format(path: Path, source_format: str | None) -> str:
    if source_format and source_format != "auto":
        fmt = source_format.lower()
        if fmt not in {"csv", "json"}:
            raise ValueError("source_format must be one of: auto, csv, json")
        return fmt
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    raise ValueError(f"Cannot infer source format from '{path.name}'. Use --format.")


def _load_rows(path: Path, source_format: str) -> list[dict]:
    if source_format == "csv":
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            return list(reader)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("points", "rows", "records", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
        return [payload]
    raise ValueError("JSON input must be an array of objects or an object with points/rows/records/data")


def _get_mapped_value(row: dict, source_field: str):
    value = row
    for part in source_field.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _normalize_signal_unit(signal: str, unit: str) -> str:
    normalized = unit.strip().lower()
    aliases = {
        "torque_nm": {"nm": "nm", "n*m": "nm", "n_m": "nm", "lbft": "lbft", "lb-ft": "lbft"},
        "power_hp": {"hp": "hp", "kw": "kw"},
        "boost_kpa": {"kpa_g": "kpa_g", "kpag": "kpa_g", "psi_g": "psi_g", "psig": "psi_g", "bar_g": "bar_g", "barg": "bar_g"},
        "map_kpa": {"kpa_abs": "kpa_abs", "kpaa": "kpa_abs", "bar_abs": "bar_abs", "bara": "bar_abs", "psi_abs": "psi_abs", "psia": "psi_abs"},
        "lambda": {"lambda": "lambda"},
        "afr": {"afr": "afr"},
        "egt_c": {"c": "c", "degc": "c", "f": "f", "degf": "f", "k": "k"},
        "rpm": {"rpm": "rpm"},
    }
    if signal not in aliases or normalized not in aliases[signal]:
        supported = ", ".join(sorted(aliases.get(signal, {})))
        raise ValueError(f"Unsupported unit '{unit}' for {signal}. Supported: {supported}")
    return aliases[signal][normalized]


def _convert_value(signal: str, value, unit: str, *, afr_stoich: float) -> float:
    raw = float(value)
    normalized = _normalize_signal_unit(signal, unit)
    if signal == "torque_nm":
        return raw * _LBFT_TO_NM if normalized == "lbft" else raw
    if signal == "power_hp":
        return raw * _KW_TO_HP if normalized == "kw" else raw
    if signal == "boost_kpa":
        if normalized == "psi_g":
            return raw * _PSI_TO_KPA
        if normalized == "bar_g":
            return raw * 100.0
        return raw
    if signal == "map_kpa":
        if normalized == "psi_abs":
            return raw * _PSI_TO_KPA
        if normalized == "bar_abs":
            return raw * 100.0
        return raw
    if signal == "lambda":
        return raw
    if signal == "afr":
        return raw
    if signal == "egt_c":
        if normalized == "f":
            return (raw - 32.0) * 5.0 / 9.0
        if normalized == "k":
            return raw - 273.15
        return raw
    if signal == "rpm":
        return raw
    raise ValueError(f"Unsupported signal '{signal}'")


def _default_source_mapping(source_format: str) -> dict[str, str]:
    if source_format == "csv":
        return {"rpm": "rpm", "power_hp": "hp", "torque_nm": "tq"}
    return {}


def _canonicalize_rows(
    rows: list[dict],
    *,
    mapping: dict[str, str],
    units: dict[str, str],
    afr_stoich: float,
) -> tuple[list[dict], list[str], list[str]]:
    if "rpm" not in mapping:
        raise ValueError("mapping must include rpm")
    if "torque_nm" not in mapping and "power_hp" not in mapping:
        raise ValueError("mapping must include at least one of torque_nm or power_hp")

    warnings: list[str] = []
    points: list[dict] = []
    present = set()
    for index, row in enumerate(rows):
        point: dict[str, float] = {}
        rpm_raw = _get_mapped_value(row, mapping["rpm"])
        if rpm_raw in (None, ""):
            raise ValueError(f"Row {index + 1} is missing rpm")
        rpm = _convert_value("rpm", rpm_raw, units.get("rpm", "rpm"), afr_stoich=afr_stoich)
        if rpm <= 0.0:
            raise ValueError(f"Row {index + 1} has non-positive rpm")
        point["rpm"] = rpm

        for signal, source_field in mapping.items():
            if signal == "rpm":
                continue
            raw = _get_mapped_value(row, source_field)
            if raw in (None, ""):
                continue
            unit = units.get(signal)
            if unit is None:
                raise ValueError(f"Unit for mapped signal '{signal}' must be declared")
            point[signal] = _convert_value(signal, raw, unit, afr_stoich=afr_stoich)
            present.add(signal)

        if "torque_nm" not in point and "power_hp" not in point:
            raise ValueError(f"Row {index + 1} must include at least one of torque_nm or power_hp")

        if "afr" in point and "lambda" in point:
            lambda_from_afr = point["afr"] / max(float(afr_stoich), 1e-9)
            if abs(lambda_from_afr - point["lambda"]) > 0.05:
                warnings.append(
                    f"Row {index + 1} contains afr and lambda that differ by more than 0.05 lambda using afr_stoich={afr_stoich:.3f}."
                )

        points.append(point)

    for signal in mapping:
        if signal == "rpm":
            continue
        if signal not in present:
            warnings.append(f"Mapped signal '{signal}' was declared but no usable values were found in the source.")

    signals_present = sorted(signal for signal in present if signal in ALL_SIGNALS)
    return points, signals_present, warnings


def import_dyno_file(
    source_path: Path,
    *,
    source_format: str = "auto",
    mapping: dict[str, str] | None = None,
    units: dict[str, str] | None = None,
    engine_id: str | None = None,
    afr_stoich: float = 14.7,
) -> tuple[dict, dict]:
    fmt = _infer_source_format(source_path, source_format)
    rows = _load_rows(source_path, fmt)
    if not rows:
        raise ValueError("Source contains no rows")

    applied_mapping = dict(_default_source_mapping(fmt))
    if mapping:
        applied_mapping.update(mapping)
    declared_units = {"rpm": "rpm"}
    if units:
        declared_units.update(units)
    if "torque_nm" in applied_mapping and "torque_nm" not in declared_units:
        declared_units["torque_nm"] = "lbft"
    if "power_hp" in applied_mapping and "power_hp" not in declared_units:
        declared_units["power_hp"] = "hp"

    points, signals_present, warnings = _canonicalize_rows(
        rows,
        mapping=applied_mapping,
        units=declared_units,
        afr_stoich=float(afr_stoich),
    )
    payload = {"engine_id": engine_id, "points": points}
    import_trace = {
        "source_format": fmt,
        "mapping_applied": applied_mapping,
        "original_units": {key: declared_units[key] for key in applied_mapping if key in declared_units},
        "signals_present": signals_present,
        "signal_evidence": build_signal_evidence(dataset_signals=signals_present),
        "import_warnings": warnings,
        "import_timestamp": dt.datetime.utcnow().isoformat() + "Z",
        "canonical_units": dict(CANONICAL_SIGNAL_UNITS),
        "afr_stoich_reference": float(afr_stoich),
    }
    return payload, import_trace


def write_dataset_package(
    source_path: Path,
    dataset_dir: Path,
    *,
    dataset_id: str,
    engine_id: str,
    preset_path: str,
    notes: str,
    error_contract: dict,
    source_format: str = "auto",
    mapping: dict[str, str] | None = None,
    units: dict[str, str] | None = None,
    afr_stoich: float = 14.7,
) -> None:
    payload, trace = import_dyno_file(
        source_path,
        source_format=source_format,
        mapping=mapping,
        units=units,
        engine_id=engine_id,
        afr_stoich=afr_stoich,
    )
    dataset_dir.mkdir(parents=True, exist_ok=True)
    source_bytes = source_path.read_bytes()
    source_out = dataset_dir / f"source{source_path.suffix.lower() or '.dat'}"
    source_out.write_bytes(source_bytes)

    metadata = {
        "dataset_id": dataset_id,
        "engine_id": engine_id,
        "preset_path": preset_path,
        "source_type": "real_data",
        "source_file": source_out.name,
        "source_format": trace["source_format"],
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "mapping_applied": trace["mapping_applied"],
        "original_units": trace["original_units"],
        "signals_present": trace["signals_present"],
        "signal_evidence": trace["signal_evidence"],
        "import_warnings": trace["import_warnings"],
        "canonical_units": trace["canonical_units"],
        "afr_stoich_reference": trace["afr_stoich_reference"],
        "notes": notes,
        "error_contract": error_contract,
        "import_timestamp": trace["import_timestamp"],
    }
    (dataset_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (dataset_dir / "target_curve.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
