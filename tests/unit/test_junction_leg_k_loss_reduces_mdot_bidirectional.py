import math

from core.advanced.junctions import JunctionCapacitanceState, junction_leg_flux


def _pipe_prim(p: float, T: float, Y: float, gas_constant: float) -> tuple[float, float, float, float, float]:
    rho = p / (gas_constant * T)
    u = 0.0
    return rho, u, p, T, Y


def test_junction_leg_k_loss_reduces_mdot_bidirectional() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    junction = JunctionCapacitanceState(m_total=0.01, E_total=1e4, mY=0.001, p=101325.0, T=600.0, Y=0.1)
    area_face = 0.001

    prim_fwd = _pipe_prim(130000.0, 650.0, 0.2, gas_constant)
    mdot0, _, _, _, _ = junction_leg_flux(
        prim_fwd,
        area_face,
        junction,
        gamma,
        gas_constant,
        cp,
        loss_coeff=0.0,
    )
    mdot_k, _, _, _, _ = junction_leg_flux(
        prim_fwd,
        area_face,
        junction,
        gamma,
        gas_constant,
        cp,
        loss_coeff=2.0,
    )
    assert math.copysign(1.0, mdot0) == math.copysign(1.0, mdot_k)
    assert abs(mdot_k) < abs(mdot0)

    prim_rev = _pipe_prim(90000.0, 620.0, 0.2, gas_constant)
    mdot0_rev, _, _, _, _ = junction_leg_flux(
        prim_rev,
        area_face,
        junction,
        gamma,
        gas_constant,
        cp,
        loss_coeff=0.0,
    )
    mdot_k_rev, _, _, _, _ = junction_leg_flux(
        prim_rev,
        area_face,
        junction,
        gamma,
        gas_constant,
        cp,
        loss_coeff=2.0,
    )
    assert math.copysign(1.0, mdot0_rev) == math.copysign(1.0, mdot_k_rev)
    assert abs(mdot_k_rev) < abs(mdot0_rev)
