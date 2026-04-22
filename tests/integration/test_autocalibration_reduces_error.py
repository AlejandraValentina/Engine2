from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@pytest.mark.integration
def test_autocalibration_reduces_error(tmp_path: Path) -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json")
    base = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))

    target_engine = Engine.from_dict(base.to_dict())
    target_engine.head.port_flow_efficiency *= 0.8

    sim = CylinderSimulator(target_engine)
    points = []
    for rpm in (2000.0, 3000.0):
        cycle = sim.run_cycle(rpm)
        points.append({"rpm": rpm, "power_hp": float(cycle["mean_power_hp"])})

    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps({"points": points}, indent=2), encoding="utf-8")

    out_path = tmp_path / "calib_report.json"
    subprocess.check_call(
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
            "5",
            "--params",
            "ve_scale",
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["error_final"] <= report["error_initial"]
    assert int(report["evals_used"]) <= 5
    assert report["status"] in {"complete", "max_evals"}
