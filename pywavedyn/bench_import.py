from __future__ import annotations

import csv
import json
from pathlib import Path


_LBFT_TO_NM = 1.3558179483
_KW_TO_HP = 1.34102209


def import_csv(path: Path, torque_units: str = "lbft", power_units: str = "hp", engine_id: str | None = None) -> dict:
    torque_units = torque_units.lower()
    power_units = power_units.lower()
    if torque_units not in {"lbft", "nm"}:
        raise ValueError("torque_units must be 'lbft' or 'nm'")
    if power_units not in {"hp", "kw"}:
        raise ValueError("power_units must be 'hp' or 'kw'")

    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError("CSV contains no rows")

    points = []
    for row in rows:
        rpm = float(row.get("rpm", row.get("RPM", row.get("Rpm", 0.0))))
        if rpm <= 0.0:
            raise ValueError("CSV rpm must be positive")
        hp_val = row.get("hp", row.get("HP"))
        tq_val = row.get("tq", row.get("TQ", row.get("torque", row.get("Torque"))))
        if hp_val is None and tq_val is None:
            raise ValueError("CSV must include hp or tq column")
        entry = {"rpm": rpm}
        if hp_val is not None:
            hp = float(hp_val)
            if power_units == "kw":
                hp *= _KW_TO_HP
            entry["power_hp"] = hp
        if tq_val is not None:
            tq = float(tq_val)
            if torque_units == "lbft":
                tq *= _LBFT_TO_NM
            entry["torque_nm"] = tq
        points.append(entry)

    payload = {"engine_id": engine_id, "points": points}
    return payload


def write_targets(payload: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
