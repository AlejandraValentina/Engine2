from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from core.engine_components import Camshaft, CylinderHead, SimulationSettings
from core.simulator import compute_exhaust_valve_area


def test_curtain_area_zero_when_closed() -> None:
    cam = Camshaft(exhaust_lift=10.0)
    head = CylinderHead(exhaust_valves=2, exhaust_valve_diameter_mm=30.0)
    settings = SimulationSettings(exhaust_valve_area_model="curtain", exhaust_valve_cd=1.0)

    area = compute_exhaust_valve_area(0.0, cam, head, settings)
    assert area == 0.0


def test_curtain_area_scales_with_lift() -> None:
    cam_low = Camshaft(exhaust_lift=5.0)
    cam_high = Camshaft(exhaust_lift=12.0)
    head = CylinderHead(exhaust_valves=1, exhaust_valve_diameter_mm=32.0)
    settings = SimulationSettings(exhaust_valve_area_model="curtain", exhaust_valve_cd=1.0)

    center = 720.0 - (cam_low.lobe_separation + cam_low.advance)
    area_low = compute_exhaust_valve_area(center, cam_low, head, settings)
    area_high = compute_exhaust_valve_area(center, cam_high, head, settings)

    assert area_low > 0.0
    assert area_high > area_low
