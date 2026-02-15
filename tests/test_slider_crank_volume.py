import math

import pytest

from core.advanced.cylinder_cv import slider_crank_volume


def test_slider_crank_volume_handles_singular_geometry() -> None:
    theta = math.pi / 2.0
    bore = 0.086
    stroke = 0.086
    conrod = stroke / 2.0
    clearance = 1e-4

    volume, dVdtheta = slider_crank_volume(theta, bore, stroke, conrod, clearance)

    assert math.isfinite(volume)
    assert math.isfinite(dVdtheta)


def test_slider_crank_volume_rejects_nonpositive_conrod() -> None:
    with pytest.raises(ValueError, match="conrod length must be positive"):
        slider_crank_volume(0.0, 0.086, 0.086, 0.0, 1e-4)
