import pytest

from core.advanced.coupling import ValveTiming, boundary_flux_from_nozzle
from core.advanced.state import stagnation_from_static


def test_nozzle_backflow_uses_downstream_totals() -> None:
    gamma = 1.35
    R = 287.0
    cp = 1100.0

    p0 = 100000.0
    T0 = 300.0
    Y0 = 0.2

    p_down = 150000.0
    T_down = 600.0
    Y_down = 0.9
    u_down = 120.0
    p0_down, T0_down = stagnation_from_static(p_down, T_down, u_down, gamma, R)

    valve = ValveTiming(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.005,
        seat_diameter_m=0.03,
        cd=1.0,
    )

    mdot, Hdot, Ydot, _ = boundary_flux_from_nozzle(
        p0,
        T0,
        Y0,
        p_down,
        valve=valve,
        angle_deg=5.0,
        gamma=gamma,
        gas_constant=R,
        cp=cp,
        p0_down=p0_down,
        T0_down=T0_down,
        Y0_down=Y_down,
    )

    assert mdot < 0.0
    assert pytest.approx(cp * T0_down, rel=1e-6, abs=1e-9) == (Hdot / mdot)
    assert pytest.approx(Y_down, rel=1e-6, abs=1e-9) == (Ydot / mdot)
