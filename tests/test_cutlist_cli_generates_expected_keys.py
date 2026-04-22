from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

def test_cutlist_cli_generates_expected_keys(tmp_path) -> None:
    out_path = tmp_path / "cutlist.json"
    text_path = tmp_path / "cutlist.txt"
    preset = Path("presets/legacy/custom_twin_230cc.json").resolve()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "cutlist",
            "--engine",
            str(preset),
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    assert out_path.exists()
    assert text_path.exists()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    intake = payload.get("intake", {})
    exhaust = payload.get("exhaust", {})

    for key in ("runner_length_mm", "runner_diameter_mm"):
        value = float(intake.get(key, 0.0))
        assert value > 0.0

    for key in ("primary_length_mm", "primary_diameter_mm", "collector_length_mm"):
        value = float(exhaust.get(key, 0.0))
        assert value > 0.0
