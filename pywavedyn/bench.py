from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from core.engine_components import Engine
from pywavedyn.analysis_evidence import build_signal_evidence
from pywavedyn.analysis_contract import (
    REPORT_TYPE_COMPARE,
    apply_analysis_envelope,
    build_report_context,
)
from core.thermo import CylinderSimulator
from pywavedyn.combustion_mode import summarize_combustion_mode
from pywavedyn.engineering_diagnostics import diagnose_compare_report


OPTIONAL_COMPARE_SIGNALS = ("boost_kpa", "map_kpa", "lambda", "afr", "egt_c")


@dataclass
class BenchReport:
    metadata: dict
    dataset: dict
    points: list[dict]
    errors: dict
    contract: dict
    signal_coverage: dict | None = None
    signal_evidence: dict | None = None
    diagnostics: list[dict] | None = None

    def to_dict(self) -> dict:
        payload = {
            "metadata": self.metadata,
            "dataset": self.dataset,
            "points": self.points,
            "errors": self.errors,
            "contract": self.contract,
        }
        if self.signal_coverage is not None:
            payload["signal_coverage"] = self.signal_coverage
        if self.signal_evidence is not None:
            payload["signal_evidence"] = self.signal_evidence
        if self.diagnostics is not None:
            payload["diagnostics"] = self.diagnostics
        return apply_analysis_envelope(
            payload,
            report_type=REPORT_TYPE_COMPARE,
            context=build_report_context(dataset=self.dataset),
            generated_at_utc=str(self.metadata.get("timestamp", "")) or None,
        )


def _input_hash(raw: dict) -> str:
    payload = json.dumps(raw, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _source_hash(dataset_dir: Path, meta: dict, target: dict) -> str:
    source_file = meta.get("source_file")
    if source_file:
        source_path = dataset_dir / str(source_file)
        if source_path.exists():
            return hashlib.sha256(source_path.read_bytes()).hexdigest()
    return hashlib.sha256(json.dumps(target, sort_keys=True).encode("utf-8")).hexdigest()


def _infer_signals(points: list[dict]) -> list[str]:
    found = set()
    for point in points:
        found.update(key for key in point if key != "rpm")
    return sorted(found)


def _normalize_dataset_metadata(dataset_dir: Path, meta: dict, target: dict) -> dict:
    points = target.get("points", [])
    signals_present = meta.get("signals_present") or _infer_signals(points)
    return {
        "dataset_id": meta.get("dataset_id") or meta.get("engine_id") or dataset_dir.name,
        "engine_id": meta.get("engine_id") or meta.get("dataset_id") or dataset_dir.name,
        "preset_path": meta.get("preset_path") or meta.get("preset") or "",
        "source_type": meta.get("source_type") or meta.get("source") or "unknown",
        "source_file": meta.get("source_file") or ("target_curve.json" if not (dataset_dir / "source.csv").exists() else "source.csv"),
        "source_format": meta.get("source_format") or "canonical",
        "source_sha256": meta.get("source_sha256") or _source_hash(dataset_dir, meta, target),
        "notes": meta.get("notes", ""),
        "error_contract": meta.get("error_contract", {}),
        "mapping_applied": meta.get("mapping_applied", {}),
        "original_units": meta.get("original_units") or meta.get("units", {}),
        "signals_present": signals_present,
        "signal_evidence": meta.get("signal_evidence") or build_signal_evidence(dataset_signals=signals_present),
        "import_warnings": meta.get("import_warnings", []),
        "canonical_units": meta.get("canonical_units", {}),
        "import_timestamp": meta.get("import_timestamp"),
        "metadata": meta,
    }


def _load_dataset_package(dataset_dir: Path) -> tuple[dict, dict]:
    meta = _load_json(dataset_dir / "metadata.json")
    target = _load_json(dataset_dir / "target_curve.json")
    normalized = _normalize_dataset_metadata(dataset_dir, meta, target)

    required_meta = [
        "dataset_id",
        "engine_id",
        "preset_path",
        "source_type",
        "source_file",
        "source_sha256",
        "notes",
        "error_contract",
    ]
    missing = [key for key in required_meta if key not in normalized]
    if missing:
        raise ValueError(f"metadata.json missing required keys: {', '.join(missing)}")
    if not isinstance(normalized.get("error_contract"), dict):
        raise ValueError("metadata.json error_contract must be an object")
    return normalized, target


def _mape(errors: list[float]) -> float:
    if not errors:
        return 0.0
    return float(sum(errors) / max(len(errors), 1))


def _mae(errors: list[float]) -> float:
    if not errors:
        return 0.0
    return float(sum(abs(e) for e in errors) / max(len(errors), 1))


def _predicted_optional_signal(engine: Engine, cycle: dict, signal: str) -> float | None:
    if signal == "boost_kpa":
        value = cycle.get("boost_kpa")
        return float(value) if value is not None else None
    if signal == "map_kpa":
        value = cycle.get("map_est_kpa")
        return float(value) if value is not None else None
    if signal == "afr":
        return float(getattr(engine.combustion, "afr", getattr(engine.fuel, "stoich_afr", 14.7)))
    if signal == "lambda":
        afr = float(getattr(engine.combustion, "afr", getattr(engine.fuel, "stoich_afr", 14.7)))
        stoich = max(float(getattr(engine.fuel, "stoich_afr", 14.7)), 1e-9)
        return afr / stoich
    if signal == "egt_c":
        return None
    return None


def _evaluate_with_engine(engine: Engine, engine_raw: dict, dataset_dir: Path) -> BenchReport:
    dataset_dir = dataset_dir.resolve()
    meta, target = _load_dataset_package(dataset_dir)
    points = target.get("points", [])
    if not isinstance(points, list) or not points:
        raise ValueError("target_curve.json must include non-empty points list")

    sim = CylinderSimulator(engine)
    torque_errors: list[float] = []
    power_errors: list[float] = []
    optional_errors: dict[str, list[float]] = {}
    compared_signals = {"torque_nm", "power_hp"}
    skipped_signals = set()
    point_entries: list[dict] = []

    for pt in points:
        rpm = float(pt["rpm"])
        cycle = sim.run_cycle(rpm)
        predicted = {
            "torque_nm": float(cycle["mean_torque_nm"]),
            "power_hp": float(cycle["mean_power_hp"]),
        }
        target_vals = {}
        if "torque_nm" in pt:
            target_vals["torque_nm"] = float(pt["torque_nm"])
            denom = max(abs(target_vals["torque_nm"]), 1e-9)
            torque_errors.append(abs(predicted["torque_nm"] - target_vals["torque_nm"]) / denom)
        if "power_hp" in pt:
            target_vals["power_hp"] = float(pt["power_hp"])
            denom = max(abs(target_vals["power_hp"]), 1e-9)
            power_errors.append(abs(predicted["power_hp"] - target_vals["power_hp"]) / denom)

        for signal in OPTIONAL_COMPARE_SIGNALS:
            if signal not in pt:
                continue
            target_value = float(pt[signal])
            target_vals[signal] = target_value
            predicted_value = _predicted_optional_signal(engine, cycle, signal)
            if predicted_value is None:
                skipped_signals.add(signal)
                continue
            predicted[signal] = predicted_value
            denom = max(abs(target_value), 1e-9)
            optional_errors.setdefault(signal, []).append(abs(predicted_value - target_value) / denom)
            compared_signals.add(signal)

        point_entries.append({"rpm": rpm, "target": target_vals, "predicted": predicted})

    errors = {
        "torque_nm": {"mae": _mae(torque_errors), "mape": _mape(torque_errors)},
        "power_hp": {"mae": _mae(power_errors), "mape": _mape(power_errors)},
    }
    total_mape = _mape([errors["torque_nm"]["mape"], errors["power_hp"]["mape"]])
    errors["total_mape"] = total_mape
    if optional_errors:
        errors["optional_signals"] = {
            signal: {"mae": _mae(vals), "mape": _mape(vals), "count": len(vals)}
            for signal, vals in sorted(optional_errors.items())
        }

    contract_cfg = meta.get("error_contract", {})
    torque_limit = float(contract_cfg.get("torque_mape_max", 1.0))
    power_limit = float(contract_cfg.get("power_mape_max", 1.0))
    contract_pass = errors["torque_nm"]["mape"] <= torque_limit and errors["power_hp"]["mape"] <= power_limit

    metadata = {
        "input_hash": _input_hash(engine_raw),
        "timestamp": dt.datetime.utcnow().isoformat() + "Z",
        "version": "unknown",
        "settings": engine.simulation_settings.to_dict(),
        "coupling_mode": "benchmark",
        "combustion": summarize_combustion_mode(engine),
    }
    dataset_info = {
        "dataset_id": meta["dataset_id"],
        "engine_id": meta["engine_id"],
        "preset_path": meta["preset_path"],
        "source_type": meta["source_type"],
        "source_file": meta["source_file"],
        "source_format": meta.get("source_format"),
        "source_sha256": meta["source_sha256"],
        "notes": meta["notes"],
        "error_contract": meta["error_contract"],
        "signals_present": meta.get("signals_present", []),
        "mapping_applied": meta.get("mapping_applied", {}),
        "original_units": meta.get("original_units", {}),
        "import_warnings": meta.get("import_warnings", []),
        "signal_evidence": meta.get("signal_evidence", {}),
        "path": str(dataset_dir),
        "metadata": meta["metadata"],
    }

    signal_evidence = build_signal_evidence(
        dataset_signals=meta.get("signals_present", []),
        compared_signals=sorted(compared_signals),
        skipped_signals=sorted(skipped_signals),
    )

    report = BenchReport(
        metadata=metadata,
        dataset=dataset_info,
        points=point_entries,
        errors=errors,
        contract={
            "torque_mape_max": torque_limit,
            "power_mape_max": power_limit,
            "pass": bool(contract_pass),
        },
        signal_coverage={
            "dataset_signals": meta.get("signals_present", []),
            "compared_signals": sorted(compared_signals),
            "skipped_signals": sorted(skipped_signals),
        },
        signal_evidence=signal_evidence,
    )
    report.diagnostics = diagnose_compare_report(report.to_dict())
    return report


def evaluate(engine_path: Path, dataset_dir: Path) -> BenchReport:
    engine_raw = _load_json(engine_path)
    engine = Engine.from_dict(engine_raw)
    return _evaluate_with_engine(engine, engine_raw, dataset_dir)


def evaluate_with_engine(engine: Engine, engine_raw: dict, dataset_dir: Path) -> BenchReport:
    return _evaluate_with_engine(engine, engine_raw, dataset_dir)
