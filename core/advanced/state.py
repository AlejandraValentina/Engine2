from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Conserved1D:
    rho: float
    rhou: float
    rhoE: float
    rhoY: float


@dataclass
class Primitive1D:
    rho: float
    u: float
    p: float
    T: float
    Y: float


def primitive_to_conserved(prim: Primitive1D, gamma: float, gas_constant: float) -> Conserved1D:
    if prim.rho <= 0:
        raise ValueError("rho must be positive")
    e_int = gas_constant * prim.T / (gamma - 1.0)
    E = e_int + 0.5 * prim.u * prim.u
    return Conserved1D(
        rho=prim.rho,
        rhou=prim.rho * prim.u,
        rhoE=prim.rho * E,
        rhoY=prim.rho * prim.Y,
    )


def conserved_to_primitive(cons: Conserved1D, gamma: float, gas_constant: float) -> Primitive1D:
    if cons.rho <= 0:
        raise ValueError("rho must be positive")
    u = cons.rhou / cons.rho
    E = cons.rhoE / cons.rho
    e_int = E - 0.5 * u * u
    T = max(e_int * (gamma - 1.0) / gas_constant, 1e-9)
    p = cons.rho * gas_constant * T
    Y = cons.rhoY / cons.rho
    return Primitive1D(rho=cons.rho, u=u, p=p, T=T, Y=Y)


def clamp_boundary_Y(prim: Primitive1D) -> Primitive1D:
    Y = min(max(prim.Y, 0.0), 1.0)
    return Primitive1D(rho=prim.rho, u=prim.u, p=prim.p, T=prim.T, Y=Y)
