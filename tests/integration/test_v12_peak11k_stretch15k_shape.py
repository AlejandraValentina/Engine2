from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest


PRESET_PATH = Path("presets/v12_1710cc_peak11k_stretch15k.json")
RPM_POINTS = [9000, 11000, 13000, 15000]


def _assert_no_knock_yes(knock_entry: dict) -> None:
    for key in ("knock_flag", "knock_warning", "knock"):
        if key not in knock_entry:
            continue
        value = knock_entry[key]
        if isinstance(value, str):
            assert value.strip().upper() != "YES", f"{key} is YES"
        else:
            assert not bool(value), f"{key} indicates knock"


def _run_dyno_point(tmp_path: Path, rpm: int) -> dict:
    dyno_path = tmp_path / f"dyno_{rpm}.json"
    cmd = [
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
        str(dyno_path),
    ]

    subprocess.run(cmd, check=True, capture_output=True, text=True)

    dyno_payload = json.loads(dyno_path.read_text(encoding="utf-8"))
    dyno_results = dyno_payload.get("results", [])
    assert len(dyno_results) == 1, f"unexpected dyno rows for {rpm}: {len(dyno_results)}"
    return dyno_results[0]


@pytest.mark.integration
def test_v12_peak11k_stretch15k_shape(tmp_path: Path) -> None:
    power_by_rpm: dict[int, float] = {}
    for rpm in RPM_POINTS:
        dyno_entry = _run_dyno_point(tmp_path, rpm)

        for key in ("mean_power_hp", "mean_torque_nm", "bmep_bar", "ve_actual"):
            value = float(dyno_entry.get(key, 0.0))
            assert math.isfinite(value), f"{key} not finite at {rpm}: {value}"
        power_by_rpm[rpm] = float(dyno_entry["mean_power_hp"])

        _assert_no_knock_yes(dyno_entry)
        for value in dyno_entry.values():
            if isinstance(value, bool):
                continue
            if isinstance(value, (float, int)):
                assert math.isfinite(float(value))

    max_power = max(power_by_rpm.values())
    power_11k = power_by_rpm[11000]
    power_15k = power_by_rpm[15000]

    assert power_11k >= 0.97 * max_power
    assert power_15k >= 0.85 * power_11k
