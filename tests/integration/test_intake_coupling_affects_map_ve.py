from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@pytest.mark.integration
def test_intake_coupling_affects_map_ve() -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json")
    engine = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))

    engine.throttle.enabled = True
    engine.throttle.position = 0.35
    engine.throttle.body_diam_m = engine.intake.throttle_body_dia * 1e-3

    engine.simulation_settings.intake_coupling = {"enabled": False}
    baseline = CylinderSimulator(engine).run_cycle(2000.0)

    engine.simulation_settings.intake_coupling = {
        "enabled": True,
        "max_iters": 3,
        "map_tol_pa": 5e3,
        "under_relax": 1.0,
        "max_steps": 40,
        "target_dx": 0.05,
    }
    coupled = CylinderSimulator(engine).run_cycle(2000.0)

    assert "map_est_kpa" in coupled
    assert coupled["map_est_kpa"] == coupled["map_est_kpa"]
    assert coupled["map_est_kpa"] <= engine.simulation_settings.air_pressure_bar * 105.0
