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
    for mdot in (1e-12, -1e-12):
        U = ghost_state_from_nozzle(p0, T0, Y0, mdot, area_face, gamma, R, phase="phase2")
        prim = conserved_to_primitive(Conserved1D(U[0], U[1], U[2], U[3]), gamma, R)

        mdot_recon = prim.rho * prim.u * area_face
        assert mdot_recon == pytest.approx(mdot, rel=1e-2, abs=1e-12)
        assert prim.p > 0.0
        assert prim.T > 0.0
