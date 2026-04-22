import pytest

from core.advanced.coupling import ValveTiming, boundary_flux_from_nozzle


def test_cd_applied_once_in_valve_area() -> None:
    gamma = 1.35
    R = 287.0
    cp = 1100.0

    base = dict(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.005,
        seat_diameter_m=0.03,
    )

    valve_cd1 = ValveTiming(**base, cd=1.0)
    valve_cd05 = ValveTiming(**base, cd=0.5)

    mdot1, _, _, _ = boundary_flux_from_nozzle(
        140000.0,
        600.0,
        0.2,
        100000.0,
        valve=valve_cd1,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
    )
    mdot05, _, _, _ = boundary_flux_from_nozzle(
        140000.0,
        600.0,
        0.2,
        100000.0,
        valve=valve_cd05,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
    )

    assert mdot1 > 0.0
    assert mdot05 > 0.0
    assert mdot05 == pytest.approx(0.5 * mdot1, rel=1e-3, abs=1e-9)
