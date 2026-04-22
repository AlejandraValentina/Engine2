from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@pytest.mark.integration
def test_optimize_reduces_error(tmp_path: Path) -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json")
    base = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))

    target_engine = Engine.from_dict(base.to_dict())
    target_engine.intake.runner_length *= 1.4

    sim = CylinderSimulator(target_engine)
    points = []
    for rpm in (2500.0, 3500.0):
        cycle = sim.run_cycle(rpm)
        points.append({"rpm": rpm, "power_hp": float(cycle["mean_power_hp"])})

    target_path = tmp_path / "target.json"
    target_path.write_text(json.dumps({"points": points}, indent=2), encoding="utf-8")

    out_path = tmp_path / "opt_report.json"
    subprocess.check_call(
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
            "8",
            "--out",
            str(out_path),
        ]
    )

    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["error_best"] <= report["error_initial"]
    assert int(report["evals_used"]) <= 8
    assert report["status"] in {"complete", "max_evals"}
