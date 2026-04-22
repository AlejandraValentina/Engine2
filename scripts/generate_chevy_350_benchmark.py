#!/usr/bin/env python3
"""Generate the chevy_350_na benchmark dataset from the current simulator."""
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.engine_components import Engine
from core.thermo import CylinderSimulator

PRESET = REPO_ROOT / "presets/chevy_350.json"
OUT_DIR = REPO_ROOT / "benchmarks/datasets/chevy_350_na"
RPMS = [1500, 2000, 2500, 3000, 3500, 4000, 4500, 5000]


def main() -> None:
    engine = Engine.from_dict(json.loads(PRESET.read_text(encoding="utf-8")))
    sim = CylinderSimulator(engine)

    points = []
    for rpm in RPMS:
        cycle = sim.run_cycle(float(rpm))
        pt = {
            "rpm": float(rpm),
            "torque_nm": round(float(cycle["mean_torque_nm"]), 6),
            "power_hp": round(float(cycle["mean_power_hp"]), 6),
            "bmep_bar": round(float(cycle["bmep_bar"]), 6),
            "ve_actual": round(float(cycle["ve_actual"]), 6),
        }
        points.append(pt)
        print(
            f"  {rpm:>5} RPM -> {pt['torque_nm']:>10.4f} Nm  "
            f"{pt['power_hp']:>10.4f} hp  {pt['bmep_bar']:>8.4f} bar  VE {pt['ve_actual']:.4f}"
        )

    out_path = OUT_DIR / "target_curve.json"
    payload = {"engine_id": "chevy_350_na", "points": points}
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nWritten {len(points)} points to {out_path}")

    meta_path = OUT_DIR / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["source"] = "regression_golden"
    meta["preset"] = "presets/chevy_350.json"
    meta["notes"] = (
        "8-point regression golden dataset generated from current simulator. "
        "Regenerate with: python scripts/generate_chevy_350_benchmark.py"
    )
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Updated metadata in {meta_path}")


if __name__ == "__main__":
    main()
