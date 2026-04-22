import math

from core.thermo import (
    thermally_perfect_e,
    thermally_perfect_gamma,
    thermally_perfect_T_from_e,
)
from core.advanced.state import speed_of_sound


def test_nasa_roundtrip_T_e_T() -> None:
    gas_constant = 287.0
    for T in (300.0, 1200.0, 2500.0):
        e = thermally_perfect_e(T, 1.0, gas_constant)
        T_back, iters = thermally_perfect_T_from_e(
            e, 1.0, gas_constant, T_guess=T, return_iterations=True
        )
        rel_err = abs(T_back - T) / max(T, 1e-9)
        assert rel_err < 1e-4
        assert iters <= 5


def test_gamma_drops_with_T() -> None:
    gas_constant = 287.0
    gamma_low = thermally_perfect_gamma(300.0, 1.0, gas_constant)
    gamma_high = thermally_perfect_gamma(2000.0, 1.0, gas_constant)
    assert gamma_low > gamma_high


def test_sound_speed_reasonable() -> None:
    gas_constant = 287.0
    a_low = speed_of_sound(1.4, gas_constant, 300.0, cp_model="nasa7", Y_fresh=1.0)
    a_high = speed_of_sound(1.4, gas_constant, 2000.0, cp_model="nasa7", Y_fresh=1.0)
    assert math.isfinite(a_low)
    assert math.isfinite(a_high)
    assert a_high > a_low
