import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.solver_1d import _friction_factor_swamee_jain


def test_friction_factor_monotonic_with_Re() -> None:
    Re = np.array([5e3, 5e4, 5e5])
    f = _friction_factor_swamee_jain(Re, roughness=1e-5, diameter=0.05)

    assert f[0] > f[1] > f[2]
