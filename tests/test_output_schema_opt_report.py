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
def test_output_schema_opt_report(tmp_path: Path) -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json")
    base = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))

    target_engine = Engine.from_dict(base.to_dict())
    target_engine.intake.runner_length *= 1.2

    sim = CylinderSimulator(target_engine)
    cycle = sim.run_cycle(3000.0)
    target = {"points": [{"rpm": 3000.0, "power_hp": float(cycle["mean_power_hp"])}]}

    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps(target, indent=2), encoding="utf-8")

    out_path = tmp_path / "opt_report.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "optimize",
            "--engine",
            str(preset),
            "--target",
            str(target_path),
            "--param",
            "intake.runner_length",
            "--bounds",
            "0.20,0.60",
            "--seed",
            "123",
            "--max-evals",
            "4",
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = _load_schema("opt_report.schema.json")
    jsonschema.validate(instance=payload, schema=schema)
