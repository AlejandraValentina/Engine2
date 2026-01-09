import pytest

from core.advanced.coupling import ghost_state_from_nozzle
from core.advanced.state import Conserved1D, conserved_to_primitive


def test_ghost_state_from_nozzle_matches_mdot_phase2() -> None:
    gamma = 1.35
    R = 287.0
    p0 = 120000.0
    T0 = 600.0
    Y0 = 0.3
    mdot = 0.2
    area_face = 0.01

    U = ghost_state_from_nozzle(p0, T0, Y0, mdot, area_face, gamma, R)
    prim = conserved_to_primitive(Conserved1D(U[0], U[1], U[2], U[3]), gamma, R)

    mdot_recon = prim.rho * prim.u * area_face
    assert mdot_recon == pytest.approx(mdot, rel=1e-3, abs=1e-9)
    assert prim.p <= p0
    assert prim.T <= T0
    assert pytest.approx(Y0, rel=1e-6, abs=1e-9) == prim.Y
