import pytest

np = pytest.importorskip("numpy")

from core import numerics


def test_heat_transfer_term_zero_when_disabled():
    gamma = numerics.DEFAULT_GAMMA
    rho = 1.2
    u = 30.0
    pressure = 101325.0
    energy = pressure / (gamma - 1.0) / rho + 0.5 * u * u
    U = np.array([rho, rho * u, rho * energy], dtype=np.float64)

    D = 0.05
    f = 0.02
    Tw = 800.0
    dx = 0.1

    S = numerics.source_terms(U, dx, D, f, Tw, False)

    friction = -0.5 * rho * u * abs(u) * f / D
    assert S[2] == pytest.approx(friction * u)
