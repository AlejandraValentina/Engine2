from core.advanced.junctions import JunctionLegConfig, apply_junction_loss
from core.advanced.nozzle import mdot_mag_from_totals


def test_junction_leg_k_manual_reduces_mdot_no_flip() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    p0_up = 170000.0
    T0_up = 600.0
    p_down = 100000.0
    area_eff = 9.0e-5
    rho_down = 1.15
    mdot_base = mdot_mag_from_totals(p0_up, T0_up, p_down, area_eff, gamma, gas_constant)
    leg = JunctionLegConfig(k_loss=4.0)

    mdot, _, _ = apply_junction_loss(
        mdot_base,
        p0_up,
        T0_up,
        0.6,
        p_down,
        area_eff,
        gamma,
        gas_constant,
        cp,
        loss_coeff=leg.effective_k_loss(),
        rho_down=rho_down,
        u_down=20.0,
    )
    assert mdot > 0.0
    assert abs(mdot) < abs(mdot_base)

    mdot_rev, _, _ = apply_junction_loss(
        -mdot_base,
        p0_up,
        T0_up,
        0.6,
        p_down,
        area_eff,
        gamma,
        gas_constant,
        cp,
        loss_coeff=leg.effective_k_loss(),
        rho_down=rho_down,
        u_down=-20.0,
    )
    assert mdot_rev < 0.0
    assert abs(mdot_rev) < abs(mdot_base)
