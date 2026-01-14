import math

from core.advanced.junctions import JunctionFlow, apply_junction_loss, mix_junction_totals
from core.advanced.nozzle import mdot_mag_from_totals


def test_junction_mixing_conserves_mass_energy_scalar() -> None:
    cp = 1000.0
    inflows = [
        JunctionFlow(mdot=1.0, p0=120000.0, T0=400.0, Y0=0.2),
        JunctionFlow(mdot=3.0, p0=140000.0, T0=500.0, Y0=0.8),
    ]
    p0_mix, T0_mix, Y_mix = mix_junction_totals(inflows, cp)
    assert math.isclose(p0_mix, (1.0 * 120000.0 + 3.0 * 140000.0) / 4.0)
    assert math.isclose(T0_mix, (1.0 * 400.0 + 3.0 * 500.0) / 4.0)
    assert math.isclose(Y_mix, (1.0 * 0.2 + 3.0 * 0.8) / 4.0)


def test_junction_loss_reduces_mdot_no_flip() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    p0_up = 180000.0
    T0_up = 600.0
    p_down = 100000.0
    area_eff = 1.0e-4
    mdot_base = mdot_mag_from_totals(p0_up, T0_up, p_down, area_eff, gamma, gas_constant)
    rho_down = 1.2

    mdot_fwd, _, _ = apply_junction_loss(
        mdot_base,
        p0_up,
        T0_up,
        0.3,
        p_down,
        area_eff,
        gamma,
        gas_constant,
        cp,
        loss_coeff=2.0,
        rho_down=rho_down,
        u_down=25.0,
    )
    assert mdot_fwd > 0.0
    assert abs(mdot_fwd) < abs(mdot_base)

    mdot_rev, _, _ = apply_junction_loss(
        -mdot_base,
        p0_up,
        T0_up,
        0.3,
        p_down,
        area_eff,
        gamma,
        gas_constant,
        cp,
        loss_coeff=2.0,
        rho_down=rho_down,
        u_down=-25.0,
    )
    assert mdot_rev < 0.0
    assert abs(mdot_rev) < abs(mdot_base)
