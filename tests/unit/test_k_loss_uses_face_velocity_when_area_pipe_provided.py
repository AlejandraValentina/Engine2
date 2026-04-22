import pytest

from core.advanced.coupling import ValveTiming, boundary_flux_from_nozzle


def test_k_loss_uses_face_velocity_when_area_pipe_provided() -> None:
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

    base_args = dict(
        p0=140000.0,
        T0=600.0,
        Y0=0.2,
        p_down=100000.0,
        valve=valve,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
        p0_down=120000.0,
        T0_down=500.0,
        Y0_down=0.8,
        rho_down=1.2,
        u_down=0.0,
    )

    mdot_base, _, _, _ = boundary_flux_from_nozzle(
        **base_args,
        loss_coeff=0.0,
    )
    mdot_fallback, _, _, _ = boundary_flux_from_nozzle(
        **base_args,
        loss_coeff=2.0,
    )
    mdot_face, _, _, _ = boundary_flux_from_nozzle(
        **base_args,
        loss_coeff=2.0,
        area_pipe_m2=1e-3,
    )

    assert mdot_base > 0.0
    assert abs(mdot_fallback) == pytest.approx(abs(mdot_base), rel=1e-6, abs=1e-9)
    assert abs(mdot_face) < abs(mdot_fallback)
