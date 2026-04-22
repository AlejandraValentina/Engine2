from __future__ import annotations

import json
from pathlib import Path

import math

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def test_scavenging_metrics_present_when_enabled() -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json")
    engine = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))
    engine.simulation_settings.intake_coupling = {
        "enabled": True,
        "max_iters": 2,
        "map_tol_pa": 1e9,
        "under_relax": 1.0,
        "max_steps": 30,
        "target_dx": 0.05,
    }
    engine.throttle.enabled = True
    engine.throttle.position = 0.4
    engine.throttle.body_diam_m = engine.intake.throttle_body_dia * 1e-3

    sim = CylinderSimulator(engine)
    cycle = sim.run_cycle(2000.0)
    for key in ("overlap_flow_kg", "residual_fraction_est", "scavenging_index"):
        assert key in cycle
        assert math.isfinite(float(cycle[key]))
        assert cycle[key] >= 0.0
