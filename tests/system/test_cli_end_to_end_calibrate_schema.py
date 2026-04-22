from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator

jsonschema = pytest.importorskip("jsonschema")
pytest.importorskip("numpy")


@pytest.mark.system
def test_cli_end_to_end_calibrate_schema(tmp_path: Path) -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json").resolve()
    engine = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))
    cycle = CylinderSimulator(engine).run_cycle(2000.0)
    target = {"points": [{"rpm": 2000.0, "power_hp": float(cycle["mean_power_hp"])}]}

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
    schema = json.loads(Path("schemas/calib_report.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
