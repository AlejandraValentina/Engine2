import pytest

from core.advanced.coupling import ghost_state_from_nozzle
from core.advanced.state import Conserved1D, conserved_to_primitive


def _mdot_from_ghost(U, area):
    prim = conserved_to_primitive(Conserved1D(U[0], U[1], U[2], U[3]), 1.35, 287.0)
    return prim.rho * prim.u * area


def test_ghost_inversion_matches_target_mdot_phase2() -> None:
    gamma = 1.35
    R = 287.0
    p0 = 140000.0
    T0 = 700.0
    Y0 = 0.4
    area = 0.015

    targets = [0.02, 2e-4]
    for mdot in targets:
        U = ghost_state_from_nozzle(p0, T0, Y0, mdot, area, gamma, R, phase="phase2")
        mdot_recon = _mdot_from_ghost(U, area)
        rel_err = abs(mdot_recon - mdot) / max(abs(mdot), 1e-12)
        assert rel_err <= 1e-3
