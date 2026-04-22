from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("numpy")


PRESET = Path("presets/legacy/custom_twin_230cc.json")


def test_intake_scope_smoke(tmp_path: Path) -> None:
    out_path = tmp_path / "intake_scope.json"

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "intake-scope",
            "--engine",
            str(PRESET),
            "--target-dx",
            "0.05",
            "--max-steps",
            "30",
            "--out",
            str(out_path),
        ]
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert "metadata" in payload
    assert "time" in payload
    assert "plenum_pressure_pa" in payload
    assert "runner_pressure_pa" in payload
    assert len(payload["time"]) > 0
    assert len(payload["plenum_pressure_pa"]) == len(payload["time"])
    assert len(payload["runner_pressure_pa"]) == len(payload["time"])
    assert payload["metadata"]["coupling_mode"] == "intake_scope"
    assert np.isfinite(payload["plenum_pressure_pa"]).all()
    assert np.isfinite(payload["runner_pressure_pa"]).all()
