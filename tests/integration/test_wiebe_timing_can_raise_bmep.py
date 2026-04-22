from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator


FIXTURE_PATH = Path("tests/fixtures/v12_wiebe_bmep_fixture.json")


@pytest.mark.integration
def test_wiebe_timing_can_raise_bmep() -> None:
    raw_base = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    raw_base.setdefault("combustion", {}).setdefault("wiebe", {})["enabled"] = False

    raw_wiebe = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    wiebe_cfg = raw_wiebe.setdefault("combustion", {}).setdefault("wiebe", {})
    wiebe_cfg["enabled"] = True
    wiebe_cfg["ca50_deg_atdc"] = 9.0
    wiebe_cfg["burn_duration_deg"] = 24.0
    wiebe_cfg["eta_scale"] = 1.33

    rpm = 10000.0
    cycle_default = CylinderSimulator(Engine.from_dict(raw_base)).run_cycle(rpm)
    cycle_wiebe = CylinderSimulator(Engine.from_dict(raw_wiebe)).run_cycle(rpm)

    bmep_default = float(cycle_default["bmep_bar"])
    bmep_wiebe = float(cycle_wiebe["bmep_bar"])

    assert math.isfinite(bmep_default)
    assert math.isfinite(bmep_wiebe)
    assert bmep_wiebe >= 12.0
    assert bmep_wiebe >= bmep_default + 1.5
