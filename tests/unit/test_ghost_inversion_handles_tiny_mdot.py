import pytest

from core.advanced.coupling import ghost_state_from_nozzle
from core.advanced.state import Conserved1D, conserved_to_primitive


def test_ghost_inversion_handles_tiny_mdot() -> None:
    gamma = 1.35
    R = 287.0
    p0 = 120000.0
    T0 = 600.0
    Y0 = 0.3
    area_face = 0.02
    mdot = 1e-9

    U = ghost_state_from_nozzle(p0, T0, Y0, mdot, area_face, gamma, R)
    prim = conserved_to_primitive(Conserved1D(U[0], U[1], U[2], U[3]), gamma, R)

    mdot_recon = prim.rho * prim.u * area_face
    assert abs(mdot_recon) <= max(1e-8, 10.0 * mdot)
    assert prim.p <= p0
    assert prim.T <= T0
