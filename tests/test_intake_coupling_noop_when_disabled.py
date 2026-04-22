from __future__ import annotations

import json
from pathlib import Path

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def test_intake_coupling_noop_when_disabled(monkeypatch) -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json")
    engine = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))
    engine.simulation_settings.intake_coupling = {"enabled": False}
    monkeypatch.setattr(
        "core.intake_coupling.run_intake_coupled_cycle",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("coupling should be disabled")),
    )
    sim = CylinderSimulator(engine)
    cycle = sim.run_cycle(2000.0)
    assert "map_est_kpa" not in cycle
    assert "overlap_flow_kg" not in cycle
    assert "scavenging_index" not in cycle
