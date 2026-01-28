from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("numpy")


@pytest.mark.integration
def test_headless_partload_map_generates_grid(tmp_path: Path) -> None:
    out_path = tmp_path / "map.json"
    preset = Path("presets/legacy/custom_twin_230cc.json")

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "map",
            "--engine",
            str(preset),
            "--rpm-grid",
            "2000,3000",
            "--throttle-grid",
            "0.4,1.0",
            "--out",
            str(out_path),
        ]
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    points = payload["points"]
    assert len(points) == 4

    for point in points:
        assert np.isfinite(point["rpm"])
        assert np.isfinite(point["throttle"])
        assert np.isfinite(point["torque_nm"])
        assert np.isfinite(point["power_hp"])
        assert np.isfinite(point["bmep_bar"])
        assert np.isfinite(point["ve_actual"])

    r2000 = sorted([p for p in points if int(round(p["rpm"])) == 2000], key=lambda p: p["throttle"])
    assert len(r2000) == 2
    assert r2000[1]["torque_nm"] >= r2000[0]["torque_nm"] - 1e-6
    assert r2000[1]["power_hp"] >= r2000[0]["power_hp"] - 1e-6
