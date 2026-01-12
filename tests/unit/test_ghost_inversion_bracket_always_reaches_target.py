import pytest

from core.advanced.coupling import ghost_state_from_nozzle
from core.advanced.state import Conserved1D, conserved_to_primitive, mdot_from_stagnation


def test_ghost_inversion_bracket_always_reaches_target() -> None:
    gamma = 1.35
    R = 287.0
    p0 = 150000.0
    T0 = 700.0
    Y0 = 0.3
    area = 0.02

    mdot_choked = abs(mdot_from_stagnation(p0, T0, area, 1.0, gamma, R))
    target = 1e-5 * mdot_choked

    U = ghost_state_from_nozzle(p0, T0, Y0, target, area, gamma, R, phase="phase2")
    prim = conserved_to_primitive(Conserved1D(U[0], U[1], U[2], U[3]), gamma, R)
    mdot_recon = prim.rho * prim.u * area
    rel_err = abs(mdot_recon - target) / max(abs(target), 1e-12)

    assert rel_err <= 1e-3
