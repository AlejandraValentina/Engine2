from __future__ import annotations

import numpy as np

from core.advanced.wall_thermal import _thermal_properties
from core.engine_components import WallThermalConfig


def test_wall_thermal_properties_positive() -> None:
    cfg = WallThermalConfig(
        enabled=True,
        h_model="dittus_boelter",
        mu_model="sutherland",
        mu_const=1.8e-5,
        k_th_const=0.026,
    )
    T = np.array([250.0, 300.0, 500.0, 900.0], dtype=float)
    cp_ref = 1005.0
    mu, k_th, cp = _thermal_properties(T, cfg, cp_ref)
    assert np.all(mu > 0.0)
    assert np.all(k_th > 0.0)
    assert np.all(cp > 0.0)
