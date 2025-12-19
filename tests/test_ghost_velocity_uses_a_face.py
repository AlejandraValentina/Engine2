import pytest

pytest.importorskip("numpy")

import numpy as np

from core.advanced.coupling import ghost_state_from_nozzle
from core.advanced.state import Conserved1D, conserved_to_primitive


def test_ghost_velocity_uses_face_area() -> None:
    p0 = 200000.0
    T0 = 800.0
    Y0 = 0.8
    gamma = 1.35
    R = 287.0
    area_face = 0.01
    mdot = 0.5

    U_g = ghost_state_from_nozzle(p0, T0, Y0, mdot, area_face, gamma, R)
    cons = Conserved1D(rho=U_g[0], rhou=U_g[1], rhoE=U_g[2], rhoY=U_g[3])
    prim = conserved_to_primitive(cons, gamma, R)
    rho = prim.rho
    u = prim.u

    assert mdot == pytest.approx(rho * u * area_face, rel=1e-6)
