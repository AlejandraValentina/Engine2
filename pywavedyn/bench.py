from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@dataclass
class BenchReport:
    metadata: dict
    dataset: dict
    points: list[dict]
    errors: dict
    contract: dict

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata,
            "dataset": self.dataset,
            "points": self.points,
            "errors": self.errors,
            "contract": self.contract,
        }


def _input_hash(raw: dict) -> str:
    payload = json.dumps(raw, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _mape(errors: list[float]) -> float:
    if not errors:
        return 0.0
    return float(sum(errors) / max(len(errors), 1))


def _mae(errors: list[float]) -> float:
    if not errors:
        return 0.0
    return float(sum(abs(e) for e in errors) / max(len(errors), 1))


def evaluate(engine_path: Path, dataset_dir: Path) -> BenchReport:
    engine_raw = _load_json(engine_path)
    engine = Engine.from_dict(engine_raw)

    dataset_dir = dataset_dir.resolve()
    meta = _load_json(dataset_dir / "metadata.json")
    target = _load_json(dataset_dir / "target_curve.json")
    points = target.get("points", [])
    if not isinstance(points, list) or not points:
        raise ValueError("target_curve.json must include non-empty points list")

    sim = CylinderSimulator(engine)

    torque_errors = []
    power_errors = []
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

        point_entries.append(
            {
                "rpm": rpm,
                "target": target_vals,
                "predicted": predicted,
            }
        )

    errors = {
        "torque_nm": {"mae": _mae(torque_errors), "mape": _mape(torque_errors)},
        "power_hp": {"mae": _mae(power_errors), "mape": _mape(power_errors)},
    }
    total_mape = _mape([errors["torque_nm"]["mape"], errors["power_hp"]["mape"]])
    errors["total_mape"] = total_mape

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
    }
    dataset_info = {"id": meta.get("engine_id"), "path": str(dataset_dir), "metadata": meta}

    return BenchReport(
        metadata=metadata,
        dataset=dataset_info,
        points=point_entries,
        errors=errors,
        contract={
            "torque_mape_max": torque_limit,
            "power_mape_max": power_limit,
            "pass": bool(contract_pass),
        },
    )
