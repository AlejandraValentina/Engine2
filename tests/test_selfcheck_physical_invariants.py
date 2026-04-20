from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_selfcheck_reports_physical_invariants(tmp_path: Path) -> None:
    out_path = tmp_path / "selfcheck.json"
    preset = Path("presets/legacy/custom_twin_230cc.json").resolve()
    expectations = tmp_path / "expectations.json"
    expectations.write_text(
        json.dumps({"cases": [{"file": str(preset), "rpm": [2000, 3000]}]}, indent=2),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "selfcheck",
            "--expectations",
            str(expectations),
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    invariants = payload["cases"][0]["checks"]["physical_invariants"]
    assert len(invariants) == 2
    for entry in invariants:
        assert entry["power_from_torque_consistent"] is True
        assert entry["bmep_from_torque_consistent"] is True
        assert entry["positive_absolute_pressure"] is True
        assert entry["positive_absolute_temperature"] is True
        assert entry["ve_actual_in_bounds"] is True
