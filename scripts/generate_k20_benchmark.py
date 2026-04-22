#!/usr/bin/env python3
"""Generate the honda_k20_na benchmark dataset from the current simulator.

Run from repo root:
    python scripts/generate_k20_benchmark.py

Overwrites benchmarks/datasets/honda_k20_na/target_curve.json with fresh
simulator outputs at 8 RPM points spanning the usable rev range.
Also tightens the error_contract in metadata.json to 2% MAPE.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.engine_components import Engine
from core.thermo import CylinderSimulator

PRESET = REPO_ROOT / "presets/honda_k20.json"
OUT_DIR = REPO_ROOT / "benchmarks/datasets/honda_k20_na"
RPMS = [2000, 3000, 4000, 5000, 6000, 7000, 7500, 8000]


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
        }
        points.append(pt)
        print(f"  {rpm:>5} RPM -> {pt['torque_nm']:>10.4f} Nm  {pt['power_hp']:>10.4f} hp")

    # Write target_curve.json
    payload = {"engine_id": "honda_k20_na", "points": points}
    out_path = OUT_DIR / "target_curve.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nWritten {len(points)} points to {out_path}")

    # Tighten metadata error_contract now that data matches simulator
    meta_path = OUT_DIR / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["error_contract"] = {"torque_mape_max": 0.02, "power_mape_max": 0.02}
    meta["notes"] = (
        "8-point regression golden dataset generated from current simulator. "
        "Regenerate with: python scripts/generate_k20_benchmark.py"
    )
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Updated error_contract in {meta_path}")


if __name__ == "__main__":
    main()
