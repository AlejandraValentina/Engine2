from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from core.engine_components import Engine
from core.full_network import run_full_scope


@pytest.mark.integration
def test_full_network_cross_talk_plenum() -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json")
    engine = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))
    result = run_full_scope(engine, duration_s=0.02, max_steps=200, target_dx=0.05)

    assert len(result.intake_plenum_pa) > 2
    std = float(np.std(result.intake_plenum_pa))
    assert std > 0.0
    for stat in result.runner_stats:
        assert np.isfinite(stat["intake_rms"])
        assert np.isfinite(stat["exhaust_rms"])
