from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator

jsonschema = pytest.importorskip("jsonschema")


def _load_schema(name: str) -> dict:
    path = Path("schemas") / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.integration
def test_output_schema_calib_report(tmp_path: Path) -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json")
    base = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))

    sim = CylinderSimulator(base)
    cycle = sim.run_cycle(2000.0)
    target = {"points": [{"rpm": 2000.0, "power_hp": float(cycle["mean_power_hp"]) * 0.9}]}

    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target, indent=2), encoding="utf-8")

    out_path = tmp_path / "calib_report.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "calibrate",
            "--engine",
            str(preset),
            "--target",
            str(target_path),
            "--out",
            str(out_path),
            "--max-evals",
            "3",
            "--params",
            "ve_scale",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = _load_schema("calib_report.schema.json")
    jsonschema.validate(instance=payload, schema=schema)
