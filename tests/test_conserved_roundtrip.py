import pytest

np = pytest.importorskip("numpy")

from core.advanced.state import Primitive1D, conserved_to_primitive, primitive_to_conserved


def test_conserved_roundtrip() -> None:
    prim = Primitive1D(rho=1.2, u=10.0, p=101325.0, T=300.0, Y=0.9)
    cons = primitive_to_conserved(prim, gamma=1.4, gas_constant=287.0)
    prim2 = conserved_to_primitive(cons, gamma=1.4, gas_constant=287.0)

    assert abs(prim2.rho - prim.rho) < 1e-6
    assert abs(prim2.u - prim.u) < 1e-6
    assert abs(prim2.T - prim.T) < 1e-6
    assert abs(prim2.Y - prim.Y) < 1e-6
