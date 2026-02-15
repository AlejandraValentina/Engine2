import pytest

from core.advanced.coupling import ValveTiming, boundary_flux_from_nozzle


def test_boundary_flux_from_nozzle_rejects_positional_area() -> None:
    valve = ValveTiming(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.005,
        seat_diameter_m=0.03,
        cd=1.0,
    )

    with pytest.raises(TypeError):
        boundary_flux_from_nozzle(
            100000.0,
            300.0,
            0.2,
            90000.0,
            0.01,
            valve=valve,
            angle_deg=5.0,
            gamma=1.35,
            gas_constant=287.0,
            cp=1100.0,
        )
