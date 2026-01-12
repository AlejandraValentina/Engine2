import pytest

from core.advanced.nozzle import nozzle_mass_flow


def test_nozzle_zero_area_returns_zero() -> None:
    mdot, Hdot, Ydot = nozzle_mass_flow(
        100000.0,
        300.0,
        90000.0,
        0.0,
        1.35,
        287.0,
        1100.0,
        0.2,
    )
    assert mdot == 0.0
    assert Hdot == 0.0
    assert Ydot == 0.0


def test_nozzle_negative_area_raises() -> None:
    with pytest.raises(ValueError):
        nozzle_mass_flow(
            100000.0,
            300.0,
            90000.0,
            -1e-4,
            1.35,
            287.0,
            1100.0,
            0.2,
        )
