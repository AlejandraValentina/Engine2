from __future__ import annotations

import json
from pathlib import Path

from core.engine_components import Engine
from core.full_network import build_full_network


def test_network_build_smoke() -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json")
    engine = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))
    network = build_full_network(engine)
    kinds = {node.kind for node in network.nodes}
    assert "plenum" in kinds
    assert "runner_intake" in kinds
    assert "runner_exhaust" in kinds
    assert "cylinder" in kinds
    assert len(network.edges) > 0
