import pytest

from core.advanced.state import Conserved1D, Primitive1D, clamp_boundary_Y, conserved_to_primitive, primitive_to_conserved


def test_primitive_conserved_roundtrip_nominal() -> None:
    gamma = 1.35
    R = 287.0
    rho = 1.2
    T = 320.0
    p = rho * R * T
    prim = Primitive1D(rho=rho, u=50.0, p=p, T=T, Y=0.4)
    cons = primitive_to_conserved(prim, gamma, R)
    back = conserved_to_primitive(cons, gamma, R)

    assert back.rho == pytest.approx(prim.rho, rel=1e-9, abs=1e-12)
    assert back.u == pytest.approx(prim.u, rel=1e-9, abs=1e-12)
    assert back.p == pytest.approx(prim.p, rel=1e-9, abs=1e-6)
    assert back.T == pytest.approx(prim.T, rel=1e-9, abs=1e-6)
    assert back.Y == pytest.approx(prim.Y, rel=1e-9, abs=1e-12)


def test_clamp_boundary_Y() -> None:
    prim = Primitive1D(rho=1.2, u=0.0, p=100000.0, T=300.0, Y=1.5)
    clamped = clamp_boundary_Y(prim)
    assert clamped.Y == 1.0
    assert clamped.rho == prim.rho
    assert clamped.u == prim.u
    assert clamped.p == prim.p
    assert clamped.T == prim.T
