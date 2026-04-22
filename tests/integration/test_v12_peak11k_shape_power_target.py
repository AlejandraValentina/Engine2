from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest


PRESET_PATH = Path("presets/v12_1710cc_peak11k_stretch15k.json")
RPM_POINTS = [9000, 11000, 13000, 15000]


def _run_dyno_point(tmp_path: Path, rpm: int) -> dict:
    out_path = tmp_path / f"dyno_{rpm}.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "dyno",
            "--engine",
            str(PRESET_PATH),
            "--rpm",
            str(rpm),
            "--mode",
            "v1",
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    assert len(results) == 1, f"unexpected dyno rows for {rpm}: {len(results)}"
    return results[0]


@pytest.mark.integration
def test_v12_peak11k_shape_power_target(tmp_path: Path) -> None:
    power_by_rpm: dict[int, float] = {}
    for rpm in RPM_POINTS:
        result = _run_dyno_point(tmp_path, rpm)
        for key in ("mean_power_hp", "mean_torque_nm", "bmep_bar", "ve_actual"):
            value = float(result.get(key, 0.0))
            assert math.isfinite(value), f"{key} not finite at {rpm}: {value}"
        power_by_rpm[rpm] = float(result["mean_power_hp"])

    max_power = max(power_by_rpm.values())
    power_11k = power_by_rpm[11000]
    power_15k = power_by_rpm[15000]

    assert power_11k >= 230.0
    assert power_11k >= 0.97 * max_power
    assert power_15k <= 1.05 * power_11k
