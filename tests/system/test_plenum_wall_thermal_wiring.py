from __future__ import annotations

import math

import pytest

from core.engine_components import Engine
from core.intake_scope import run_intake_scope


@pytest.mark.system
def test_plenum_wall_thermal_wiring() -> None:
    engine = Engine()
    engine.simulation_settings.intake_plenum = {
        "wall_thermal": {
            "enabled": True,
            "material": {"rho": 7800.0, "cp": 500.0},
            "thickness_m": 0.003,
            "area_m2": 0.4,
            "twall_init_k": 380.0,
            "h_model": "constant",
            "h_const_w_per_m2k": 400.0,
            "h_min": 5.0,
            "h_max": 5000.0,
        }
    }

    result = run_intake_scope(engine, max_steps=12, target_dx=0.1)
    assert result.wall_temp_k
    assert all(math.isfinite(v) for v in result.wall_temp_k)

    delta = abs(result.wall_temp_k[-1] - result.wall_temp_k[0])
    assert delta > 0.0
    assert delta < 50.0
