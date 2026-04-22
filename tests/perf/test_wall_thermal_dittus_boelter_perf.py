from __future__ import annotations

import time

import pytest

pytest.importorskip("numba")
pytest.importorskip("numpy")

import numpy as np

from core.advanced.wall_thermal import _dittus_boelter_h_array
from core.engine_components import WallThermalConfig


@pytest.mark.perf
def test_dittus_boelter_numba_perf() -> None:
    cfg = WallThermalConfig(
        enabled=True,
        h_model="dittus_boelter",
        mu_model="sutherland",
        mu_const=1.8e-5,
        k_th_const=0.026,
    )
    n = 2000
    T = np.linspace(300.0, 900.0, n)
    rho = np.full(n, 1.2)
    u = np.full(n, 40.0)
    cp_ref = 1005.0

    _ = _dittus_boelter_h_array(T, rho, u, 0.05, cfg, cp_ref)
    start = time.perf_counter()
    _ = _dittus_boelter_h_array(T, rho, u, 0.05, cfg, cp_ref)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.5
