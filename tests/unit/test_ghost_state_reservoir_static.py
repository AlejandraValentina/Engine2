import pytest

from core.advanced.coupling import ghost_state_from_nozzle
from core.advanced.state import Conserved1D, conserved_to_primitive


def test_ghost_state_from_nozzle_uses_reservoir_static() -> None:
    gamma = 1.35
    R = 287.0
    p0 = 120000.0
    T0 = 600.0
    Y0 = 0.3
    mdot = 0.2
    area_face = 0.01

    U = ghost_state_from_nozzle(p0, T0, Y0, mdot, area_face, gamma, R)
    prim = conserved_to_primitive(Conserved1D(U[0], U[1], U[2], U[3]), gamma, R)

    assert pytest.approx(p0, rel=1e-6, abs=1e-6) == prim.p
    assert pytest.approx(T0, rel=1e-6, abs=1e-6) == prim.T
    assert pytest.approx(Y0, rel=1e-6, abs=1e-9) == prim.Y
