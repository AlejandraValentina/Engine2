from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from core.advanced.nozzle import nozzle_mass_flow


def test_nozzle_area_zero_returns_zero() -> None:
    mdot, Hdot, Ydot = nozzle_mass_flow(
        p0=200000.0,
        T0=900.0,
        p_down=101325.0,
        area_eff=0.0,
        gamma=1.35,
        gas_constant=287.0,
        cp=1005.0,
        Y0=1.0,
    )

    assert mdot == 0.0
    assert Hdot == 0.0
    assert Ydot == 0.0
