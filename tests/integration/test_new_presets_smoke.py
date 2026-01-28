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
    ]
    for preset in presets:
        engine = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))
        sim = CylinderSimulator(engine)
        cycle = sim.run_cycle(3000.0)
        assert np.isfinite(cycle["pressure"]).all()
        assert np.isfinite(cycle["temperature"]).all()
