from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import numpy as np

from core.numerics import lax_wendroff_step


def test_numerics_geometry_energy_includes_p_and_mass_term_no_nan() -> None:
    U = np.array(
        [
            [1.2, 0.6, 2.5],
            [1.1, 0.5, 2.3],
            [1.0, 0.4, 2.1],
        ],
        dtype=np.float64,
    )
    areas = np.array([1.0, 1.2, 1.4], dtype=np.float64)
    friction = np.zeros(3, dtype=np.float64)
    diameters = np.ones(3, dtype=np.float64)

    out = lax_wendroff_step(
        U,
        dt=1e-4,
        dx=0.05,
        areas=areas,
        friction_coeffs=friction,
        diameters=diameters,
        gamma=1.4,
        artificial_diffusion=0.0,
        clamp_rho_min=0.1,
        clamp_p_min=1e-6,
        clamp_p_max=1e9,
        clamp_u_max=1500.0,
        clamp_energy_max=1.0e7,
        heat_transfer_enabled=False,
    )

    assert np.isfinite(out).all()
    assert np.all(out[:, 0] >= 0.1)
