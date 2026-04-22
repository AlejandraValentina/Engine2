from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("numpy")

import numpy as np

from core.engine_components import Engine
from core.thermo import CylinderSimulator


LEGACY_PRESETS = [
    Path("presets/legacy/custom_twin_230cc.json"),
    Path("presets/legacy/ferrari_355_v12.json"),
]


@pytest.mark.legacy
@pytest.mark.parametrize("preset_path", LEGACY_PRESETS)
def test_legacy_preset_load_and_run_0d(preset_path: Path) -> None:
    engine = Engine.load_from_file(str(preset_path))
    simulator = CylinderSimulator(engine)

    for rpm in (2000.0, 4000.0):
        cycle = simulator.run_cycle(rpm)

        for key in ("pressure", "temperature", "torque"):
            values = np.asarray(cycle[key], dtype=float)
            assert np.isfinite(values).all()
            if key in {"pressure", "temperature"}:
                assert float(np.min(values)) > 0.0

        mean_power = float(cycle["mean_power_hp"])
        mean_torque = float(cycle["mean_torque_nm"])
        assert np.isfinite(mean_power)
        assert np.isfinite(mean_torque)
        assert mean_power >= 0.0
        assert mean_torque >= 0.0

        ve = float(cycle.get("ve_actual", cycle.get("ve", 0.0)))
        assert np.isfinite(ve)
        assert 0.0 <= ve <= 2.0
