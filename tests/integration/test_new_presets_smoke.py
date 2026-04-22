from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@pytest.mark.integration
def test_new_presets_smoke() -> None:
    presets = [
        Path("presets/benchmark_mono_na.json"),
        Path("presets/benchmark_turbo_small.json"),
        Path("presets/swift.json"),
    ]
    for preset in presets:
        engine = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))
        sim = CylinderSimulator(engine)
        cycle = sim.run_cycle(3000.0)
        assert np.isfinite(cycle["pressure"]).all()
        assert np.isfinite(cycle["temperature"]).all()


@pytest.mark.integration
def test_swift_preset_uses_turbo_block_for_stockish_curve() -> None:
    # The Swift preset is intentionally defined through turbo.* only so Quick Dyno
    # does not depend on the deprecated supercharger-as-turbo alias.
    preset = Path("presets/swift.json")
    engine = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))
    review = engine.preflight_review(operation="dyno", mode="v1")

    assert review["errors"] == []
    assert engine.supercharger.type == "NA"
    assert engine.supercharger.boost_pressure_bar == 0.0
    assert engine.turbo.enabled is True

    sim = CylinderSimulator(engine)
    rows = []
    for rpm in range(2000, 6501, 500):
        cycle = sim.run_cycle(float(rpm))
        rows.append((rpm, float(cycle["mean_torque_nm"]), float(cycle["mean_power_hp"])))

    peak_torque = max(rows, key=lambda row: row[1])
    peak_power = max(rows, key=lambda row: row[2])
    power_6000 = next(power for rpm, _torque, power in rows if rpm == 6000)
    power_6500 = next(power for rpm, _torque, power in rows if rpm == 6500)

    assert 220.0 <= peak_torque[1] <= 235.0
    assert 135.0 <= peak_power[2] <= 140.0
    assert power_6500 <= power_6000
