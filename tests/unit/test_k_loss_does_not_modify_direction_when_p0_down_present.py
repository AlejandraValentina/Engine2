import pytest

from core.advanced.coupling import ValveTiming, boundary_flux_from_nozzle


def test_k_loss_does_not_modify_direction_when_p0_down_present() -> None:
    gamma = 1.35
    R = 287.0
    cp = 1100.0
    valve = ValveTiming(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.005,
        seat_diameter_m=0.03,
        cd=1.0,
    )

    mdot0, _, _, _ = boundary_flux_from_nozzle(
        150000.0,
        600.0,
        0.2,
        100000.0,
        valve=valve,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
        p0_down=130000.0,
        T0_down=500.0,
        Y0_down=0.8,
        loss_coeff=0.0,
        rho_down=1.2,
        u_down=50.0,
    )
    mdot1, _, _, _ = boundary_flux_from_nozzle(
        150000.0,
        600.0,
        0.2,
        100000.0,
        valve=valve,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
        p0_down=130000.0,
        T0_down=500.0,
        Y0_down=0.8,
        loss_coeff=5.0,
        rho_down=1.2,
        u_down=50.0,
    )

    assert mdot0 > 0.0
    assert mdot1 > 0.0
    assert abs(mdot1) < abs(mdot0)
