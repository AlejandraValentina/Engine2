import json
import math
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.pro_dyno_v2 import ProDynoV2Runner
from core.units import cc_to_m3


@pytest.mark.integration
def test_pro_dyno_v2_positive_power() -> None:
    preset = Path("presets/honda_k20.json").read_text(encoding="utf-8")
    engine = Engine.from_dict(json.loads(preset))
    runner = ProDynoV2Runner(
        engine,
        settings={
            "max_cycles": 2,
            "pipe_cells": 5,
            "pipe_length_m": 0.4,
            "pipe_diameter_m": 0.04,
            "dt_max": 4e-4,
        },
    )
    results = runner.run_sweep([3000])

    power = float(results["mean_power_hp"][0])
    torque = float(results["mean_torque_nm"][0])
    ve = float(results["ve_real"][0])

    disp_m3 = max(cc_to_m3(engine.block.displacement_cc), 1e-9)
    bmep_bar = torque * 4.0 * math.pi / disp_m3 / 100000.0

    assert power > 1.0
    assert torque > 5.0
    assert bmep_bar > 0.1
    assert ve > 0.0
