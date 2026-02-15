from __future__ import annotations

from dataclasses import dataclass
import math


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


def speed_of_sound(gamma: float, gas_constant: float, T: float) -> float:
    if T <= 0.0:
        raise ValueError("T must be positive")
    return math.sqrt(max(gamma * gas_constant * T, 1e-12))


def mach(u: float, gamma: float, gas_constant: float, T: float) -> float:
    a = speed_of_sound(gamma, gas_constant, T)
    return u / a


def stagnation_from_static(p: float, T: float, u: float, gamma: float, gas_constant: float) -> tuple[float, float]:
    if p <= 0.0 or T <= 0.0:
        raise ValueError("p and T must be positive")
    M = mach(u, gamma, gas_constant, T)
    T0 = T * (1.0 + 0.5 * (gamma - 1.0) * M * M)
    p0 = p * (T0 / T) ** (gamma / (gamma - 1.0))
    return float(p0), float(T0)


def static_from_stagnation_and_mach(
    p0: float, T0: float, M: float, gamma: float, gas_constant: float
) -> tuple[float, float]:
    if p0 <= 0.0 or T0 <= 0.0:
        raise ValueError("p0 and T0 must be positive")
    M2 = M * M
    T = T0 / (1.0 + 0.5 * (gamma - 1.0) * M2)
    p = p0 * (T / T0) ** (gamma / (gamma - 1.0))
    if T <= 0.0 or p <= 0.0:
        raise ValueError("Invalid static state from stagnation inputs")
    return float(p), float(T)


def mdot_from_stagnation(
    p0: float, T0: float, area: float, M: float, gamma: float, gas_constant: float
) -> float:
    if p0 <= 0.0 or T0 <= 0.0:
        raise ValueError("p0 and T0 must be positive")
    if area <= 0.0:
        raise ValueError("area must be positive")
    p, T = static_from_stagnation_and_mach(p0, T0, abs(M), gamma, gas_constant)
    rho = p / (gas_constant * T)
    a = speed_of_sound(gamma, gas_constant, T)
    u = math.copysign(abs(M) * a, M)
    return float(rho * u * area)
