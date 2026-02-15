import pytest

from core.advanced.coupling import ValveTiming, boundary_flux_from_nozzle


def test_local_loss_reduces_mdot() -> None:
    gamma = 1.35
    R = 287.0
    cp = 1100.0

    p0 = 140000.0
    T0 = 600.0
    Y0 = 0.2
    p_down = 100000.0
    rho_down = p_down / (R * 500.0)
    u_down = 80.0

    valve = ValveTiming(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.005,
        seat_diameter_m=0.03,
        cd=1.0,
    )

    mdot_base, _, _, _ = boundary_flux_from_nozzle(
        p0,
        T0,
        Y0,
        p_down,
        valve=valve,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
        loss_coeff=0.0,
        rho_down=rho_down,
        u_down=u_down,
    )

    mdot_loss, _, _, _ = boundary_flux_from_nozzle(
        p0,
        T0,
        Y0,
        p_down,
        valve=valve,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
        loss_coeff=2.0,
        rho_down=rho_down,
        u_down=u_down,
    )

    assert mdot_base > 0.0
    assert mdot_loss > 0.0
    assert mdot_loss < mdot_base
