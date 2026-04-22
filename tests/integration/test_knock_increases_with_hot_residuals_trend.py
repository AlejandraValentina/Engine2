from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from core.knock import compute_knock_index


def test_knock_increases_with_hot_residuals_trend() -> None:
    angle = np.linspace(0.0, 720.0, 721)
    temperature = np.linspace(350.0, 900.0, 721)
    rpm = 3000.0
    start_angle = 360.0

    base = compute_knock_index(
        angle,
        temperature,
        rpm,
        start_angle,
        residual_fraction=0.1,
        residual_temp_k=800.0,
        config={"A": 17.0, "B": 3800.0, "threshold": 1.0, "window_deg": 40.0, "residual_hot_k": 1.0},
    )
    hot = compute_knock_index(
        angle,
        temperature,
        rpm,
        start_angle,
        residual_fraction=0.3,
        residual_temp_k=1000.0,
        config={"A": 17.0, "B": 3800.0, "threshold": 1.0, "window_deg": 40.0, "residual_hot_k": 1.0},
    )

    assert hot["knock_index"] > base["knock_index"]
