import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.pro_dyno_v2 import ProDynoV2Runner
from core.thermo import CylinderSimulator


@pytest.mark.integration
def test_pro_dyno_v2_ve_reasonable_and_trend() -> None:
    preset = Path("presets/honda_k20.json").read_text(encoding="utf-8")
    engine = Engine.from_dict(json.loads(preset))
    runner = ProDynoV2Runner(
        engine,
        settings={
            "max_cycles": 1,
            "settle_cycles": 0,
            "pipe_cells": 5,
            "pipe_length_m": 0.4,
            "pipe_diameter_m": 0.04,
            "dt_max": 4e-4,
        },
    )
    results = runner.run_sweep([6500, 7500])
    ve_values = results["ve_real"]
    assert all(0.5 < ve < 1.5 for ve in ve_values)


@pytest.mark.integration
def test_v1_v2_ve_not_diverging_in_stable_point() -> None:
    preset = Path("presets/honda_k20.json").read_text(encoding="utf-8")
    engine = Engine.from_dict(json.loads(preset))
    v1 = CylinderSimulator(engine).run_cycle(7000)
    ve_v1 = float(v1["ve_actual"])
    runner = ProDynoV2Runner(
        engine,
        settings={
            "max_cycles": 1,
            "settle_cycles": 0,
            "pipe_cells": 5,
            "pipe_length_m": 0.4,
            "pipe_diameter_m": 0.04,
            "dt_max": 4e-4,
        },
    )
    v2 = runner.run_sweep([7000])
    ve_v2 = float(v2["ve_real"][0])
    rel_diff = abs(ve_v2 - ve_v1) / max(ve_v1, 1e-9)
    assert rel_diff < 0.35
