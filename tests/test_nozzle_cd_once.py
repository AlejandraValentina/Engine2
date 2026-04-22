import pytest

pytest.importorskip("numpy")

from core.advanced.nozzle import nozzle_mass_flow


def test_nozzle_cd_applied_once() -> None:
    gamma = 1.33
    R = 287.0
    cp = gamma * R / (gamma - 1.0)
    p0 = 200000.0
    t0 = 800.0
    A = 1e-4
    cd = 0.6

    mdot_full, _, _ = nozzle_mass_flow(p0, t0, 150000.0, A, gamma, R, cp, 1.0)
    mdot_scaled, _, _ = nozzle_mass_flow(p0, t0, 150000.0, cd * A, gamma, R, cp, 1.0)

    assert mdot_scaled == pytest.approx(mdot_full * cd, rel=1e-6)
