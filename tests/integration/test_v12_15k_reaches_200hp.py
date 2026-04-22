from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator


PRESET_PATH = Path("presets/f1_screamer_v12_1710cc_15k.json")


@pytest.mark.integration
def test_v12_15k_reaches_200hp() -> None:
    raw = json.loads(PRESET_PATH.read_text(encoding="utf-8"))
    engine = Engine.from_dict(raw)

    cycle = CylinderSimulator(engine).run_cycle(15000.0)
    power_hp = float(cycle["mean_power_hp"])
    torque_nm = float(cycle["mean_torque_nm"])
    ve = float(cycle["ve_actual"])

    assert math.isfinite(power_hp)
    assert math.isfinite(torque_nm)
    assert math.isfinite(ve)
    assert power_hp >= 200.0

    if "knock_warning" in cycle:
        assert not bool(cycle["knock_warning"])
