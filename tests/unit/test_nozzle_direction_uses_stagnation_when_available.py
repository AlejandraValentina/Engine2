import pytest

from core.advanced.nozzle import nozzle_mass_flow


def test_nozzle_direction_uses_stagnation_when_available() -> None:
    gamma = 1.35
    R = 287.0
    cp = 1100.0

    p0 = 100000.0
    T0 = 300.0
    Y0 = 0.2
    p_down = 90000.0

    p0_down = 120000.0
    T0_down = 500.0
    Y0_down = 0.8

    mdot_rev, _, _ = nozzle_mass_flow(
        p0,
        T0,
        p_down,
        1e-4,
        gamma,
        R,
        cp,
        Y0,
        p0_down=p0_down,
        T0_down=T0_down,
        Y0_down=Y0_down,
    )
    assert mdot_rev < 0.0

    mdot_fwd, _, _ = nozzle_mass_flow(
        p0,
        T0,
        p_down,
        1e-4,
        gamma,
        R,
        cp,
        Y0,
    )
    assert mdot_fwd > 0.0


def test_nozzle_forward_when_p0_higher_than_p0_down() -> None:
    gamma = 1.35
    R = 287.0
    cp = 1100.0

    p0 = 120000.0
    T0 = 300.0
    Y0 = 0.2
    p_down = 90000.0

    p0_down = 100000.0
    T0_down = 500.0
    Y0_down = 0.8

    mdot, _, _ = nozzle_mass_flow(
        p0,
        T0,
        p_down,
        1e-4,
        gamma,
        R,
        cp,
        Y0,
        p0_down=p0_down,
        T0_down=T0_down,
        Y0_down=Y0_down,
    )
    assert mdot > 0.0


def test_nozzle_direction_falls_back_to_static_within_hysteresis() -> None:
    gamma = 1.35
    R = 287.0
    cp = 1100.0

    p0 = 100000.0
    T0 = 300.0
    Y0 = 0.2
    p_down = 101000.0

    p0_down = 100050.0
    T0_down = 500.0
    Y0_down = 0.8

    mdot, _, _ = nozzle_mass_flow(
        p0,
        T0,
        p_down,
        1e-4,
        gamma,
        R,
        cp,
        Y0,
        p0_down=p0_down,
        T0_down=T0_down,
        Y0_down=Y0_down,
    )
    assert mdot < 0.0
