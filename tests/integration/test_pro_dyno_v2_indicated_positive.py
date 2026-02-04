import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.pro_dyno_v2 import ProDynoV2Runner


@pytest.mark.integration
def test_pro_dyno_v2_indicated_positive_when_combustion_on() -> None:
    preset = Path("presets/honda_k20.json").read_text(encoding="utf-8")
    engine = Engine.from_dict(json.loads(preset))
    runner = ProDynoV2Runner(
        engine,
        settings={
            "max_cycles": 2,
            "pipe_cells": 10,
            "pipe_length_m": 0.4,
            "pipe_diameter_m": 0.04,
            "dt_max": 1e-4,
        },
    )
    _, state = runner.run_point(3000)
    work_history = state["last_result"].get("indicated_work", [])
    assert work_history
    assert max(work_history) > 0.0
