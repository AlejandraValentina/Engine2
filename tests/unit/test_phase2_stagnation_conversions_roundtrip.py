import pytest

from core.advanced.state import mach, stagnation_from_static, static_from_stagnation_and_mach


def test_phase2_stagnation_conversions_roundtrip() -> None:
    gamma = 1.35
    R = 287.0
    p = 120000.0
    T = 650.0
    u = 150.0

    p0, T0 = stagnation_from_static(p, T, u, gamma, R)
    M = mach(u, gamma, R, T)
    p_back, T_back = static_from_stagnation_and_mach(p0, T0, M, gamma, R)

    assert p_back == pytest.approx(p, rel=1e-9, abs=1e-6)
    assert T_back == pytest.approx(T, rel=1e-9, abs=1e-6)
