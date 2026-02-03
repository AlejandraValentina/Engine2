import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.pro_dyno_v2 import ProDynoV2Runner


@pytest.mark.integration
def test_pro_dyno_v2_no_negative_at_low_rpm_when_stable_mode() -> None:
    preset = Path("presets/honda_k20.json").read_text(encoding="utf-8")
    engine = Engine.from_dict(json.loads(preset))
    runner = ProDynoV2Runner(
        engine,
        settings={
            "max_cycles": 2,
            "settle_cycles": 1,
            "min_periodicity": 0.35,
            "drop_invalid": True,
        },
    )
    results = runner.run_sweep([2000, 3000])
    assert results["rpm"]
    assert all(value >= 0.0 for value in results["mean_torque_nm"])


@pytest.mark.integration
def test_pro_dyno_v2_marks_not_converged_points() -> None:
    preset = Path("presets/honda_k20.json").read_text(encoding="utf-8")
    engine = Engine.from_dict(json.loads(preset))
    runner = ProDynoV2Runner(
        engine,
        settings={
            "max_cycles": 2,
            "pipe_cells": 12,
            "pipe_length_m": 0.4,
            "pipe_diameter_m": 0.038,
            "dt_max": 1e-4,
            "min_periodicity": 0.01,
            "report_status": True,
        },
    )
    results = runner.run_sweep([3000])
    assert results["status"][0] == "failed"
    assert results["reason"][0] == "not_converged"
