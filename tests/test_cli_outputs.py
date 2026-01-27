from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")


PRESET = Path("presets/legacy/custom_twin_230cc.json")


def test_cli_dyno_and_scope(tmp_path: Path) -> None:
    dyno_out = tmp_path / "dyno.json"
    scope_out = tmp_path / "scope.json"

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "dyno",
            "--engine",
            str(PRESET),
            "--rpm",
            "2000:2500:500",
            "--out",
            str(dyno_out),
        ]
    )
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "scope",
            "--engine",
            str(PRESET),
            "--rpm",
            "2000",
            "--cycles",
            "1",
            "--target-dx",
            "0.05",
            "--max-steps",
            "30",
            "--out",
            str(scope_out),
        ]
    )

    dyno_data = json.loads(dyno_out.read_text(encoding="utf-8"))
    assert "metadata" in dyno_data
    assert "results" in dyno_data
    assert dyno_data["metadata"]["input_hash"]

    scope_data = json.loads(scope_out.read_text(encoding="utf-8"))
    assert "metadata" in scope_data
    assert "pressure_matrix_pa" in scope_data
    assert scope_data["metadata"]["coupling_mode"] in {"none", "0d_to_1d_exhaust"}
