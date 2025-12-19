import pytest

pytest.importorskip("numpy")

from core.advanced.nozzle import nozzle_mass_flow


def test_nozzle_backflow_sign() -> None:
    gamma = 1.35
    R = 287.0
    cp = gamma * R / (gamma - 1.0)
    area = 1e-4
    p0 = 200000.0
    t0 = 800.0

    mdot_fwd, _, _ = nozzle_mass_flow(p0, t0, 150000.0, area, gamma, R, cp, 1.0)
    mdot_back, _, _ = nozzle_mass_flow(p0, t0, 250000.0, area, gamma, R, cp, 1.0, p0_down=250000.0, T0_down=900.0, Y0_down=0.2)

    assert mdot_fwd > 0.0
    assert mdot_back < 0.0
