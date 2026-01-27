from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")

import numpy as np


def test_cli_mode_v1_unchanged_defaults(tmp_path) -> None:
    out_path = tmp_path / "dyno_v1.json"
    preset = Path("presets/legacy/custom_twin_230cc.json").resolve()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "dyno",
            "--engine",
            str(preset),
            "--rpm",
            "2000",
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload.get("metadata", {}).get("coupling_mode") == "none"

    results = payload.get("results", [])
    assert len(results) == 1
    entry = results[0]
    for key in ("rpm", "mean_power_hp", "mean_torque_nm", "bmep_bar", "ve_actual"):
        assert key in entry
        assert np.isfinite(float(entry[key]))
    assert float(entry["rpm"]) > 0.0
