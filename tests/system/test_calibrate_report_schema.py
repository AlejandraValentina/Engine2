from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


@pytest.mark.system
def test_calibrate_report_schema(tmp_path: Path) -> None:
    engine = Path("presets/honda_k20.json").resolve()
    target_path = tmp_path / "target.json"
    target_payload = {
        "points": [
            {"rpm": 3000, "torque_nm": 180.0, "power_hp": 75.0},
            {"rpm": 6000, "torque_nm": 190.0, "power_hp": 160.0},
        ]
    }
    target_path.write_text(json.dumps(target_payload), encoding="utf-8")

    out_path = tmp_path / "calibrate_report.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "calibrate",
            "--engine",
            str(engine),
            "--target",
            str(target_path),
            "--out",
            str(out_path),
            "--max-evals",
            "12",
            "--params",
            "ve_scale,friction_scale",
            "--diagnostics",
            "--multi-start",
            "2",
            "--top-k",
            "3",
            "--eps-obj",
            "1e-2",
            "--eps-params",
            "0.05",
            "--seed",
            "123",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/calibrate_report.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
