import pytest

np = pytest.importorskip("numpy")

from core.simulator import compute_placeholder_valve_area


def test_placeholder_valve_area_within_window():
    base_area = 0.01
    area_mid = compute_placeholder_valve_area(150.0, 100.0, 200.0, base_area)
    assert area_mid == pytest.approx(base_area)

    area_start = compute_placeholder_valve_area(100.0, 100.0, 200.0, base_area)
    assert area_start == pytest.approx(0.0)

    area_outside = compute_placeholder_valve_area(250.0, 100.0, 200.0, base_area)
    assert area_outside == pytest.approx(0.0)


def test_placeholder_valve_area_wraps_window():
    base_area = 0.02
    area_wrap = compute_placeholder_valve_area(710.0, 700.0, 20.0, base_area)
    assert area_wrap > 0.0
    assert area_wrap < base_area

    area_after_wrap = compute_placeholder_valve_area(30.0, 700.0, 20.0, base_area)
    assert area_after_wrap == pytest.approx(0.0)
