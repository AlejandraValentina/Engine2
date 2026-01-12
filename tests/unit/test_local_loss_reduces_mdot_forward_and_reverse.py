import pytest

from core.advanced.coupling import ValveTiming, boundary_flux_from_nozzle


def _valve() -> ValveTiming:
    return ValveTiming(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.005,
        seat_diameter_m=0.03,
        cd=1.0,
    )


def test_local_loss_reduces_mdot_forward_and_reverse() -> None:
    gamma = 1.35
    R = 287.0
    cp = 1100.0
    valve = _valve()

    rho_down = 1.2
    u_down = 80.0

    mdot_fwd0, _, _, _ = boundary_flux_from_nozzle(
        140000.0,
        600.0,
        0.2,
        100000.0,
        valve=valve,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
        p0_down=120000.0,
        T0_down=500.0,
        Y0_down=0.8,
        loss_coeff=0.0,
        rho_down=rho_down,
        u_down=u_down,
    )
    mdot_fwd1, _, _, _ = boundary_flux_from_nozzle(
        140000.0,
        600.0,
        0.2,
        100000.0,
        valve=valve,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
        p0_down=120000.0,
        T0_down=500.0,
        Y0_down=0.8,
        loss_coeff=2.0,
        rho_down=rho_down,
        u_down=u_down,
    )
    assert mdot_fwd0 > 0.0
    assert mdot_fwd1 > 0.0
    assert abs(mdot_fwd1) < abs(mdot_fwd0)

    mdot_rev0, _, _, _ = boundary_flux_from_nozzle(
        100000.0,
        600.0,
        0.2,
        90000.0,
        valve=valve,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
        p0_down=130000.0,
        T0_down=700.0,
        Y0_down=0.9,
        loss_coeff=0.0,
        rho_down=rho_down,
        u_down=u_down,
    )
    mdot_rev1, _, _, _ = boundary_flux_from_nozzle(
        100000.0,
        600.0,
        0.2,
        90000.0,
        valve=valve,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
        p0_down=130000.0,
        T0_down=700.0,
        Y0_down=0.9,
        loss_coeff=2.0,
        rho_down=rho_down,
        u_down=u_down,
    )
    assert mdot_rev0 < 0.0
    assert mdot_rev1 < 0.0
    assert abs(mdot_rev1) < abs(mdot_rev0)
