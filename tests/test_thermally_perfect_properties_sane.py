from __future__ import annotations

from core.thermo import thermally_perfect_cp, thermally_perfect_gamma


def test_thermally_perfect_properties_sane() -> None:
    gas_constant = 287.0
    for temp_k in (300.0, 800.0, 1500.0, 2200.0):
        cp = thermally_perfect_cp(temp_k, 1.0, gas_constant)
        gamma = thermally_perfect_gamma(temp_k, 1.0, gas_constant)
        assert cp > 0.0
        assert 1.1 <= gamma <= 1.45
