import math

import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.pro_dyno_v2 import ProDynoV2Runner

pytestmark = pytest.mark.slow


def test_pro_dyno_v2_sweep_contract() -> None:
    engine = Engine()
    runner = ProDynoV2Runner(
        engine,
        settings={
            "max_cycles": 2,
            "pipe_cells": 12,
            "pipe_length_m": 0.4,
            "pipe_diameter_m": 0.038,
            "dt_max": 1e-4,
        },
    )
    rpm_values = [2000, 3000]
    results = runner.run_sweep(rpm_values)

    assert results["rpm"] == rpm_values
    for key in ("mean_power_hp", "mean_torque_nm", "ve_real", "residual_frac"):
        series = results[key]
        assert len(series) == len(rpm_values)
        assert all(math.isfinite(value) for value in series)

    assert any(abs(value) > 0.0 for value in results["mean_power_hp"])
    assert any(abs(value) > 0.0 for value in results["mean_torque_nm"])
