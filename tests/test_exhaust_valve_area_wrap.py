from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from core.engine_components import Camshaft, CylinderHead, SimulationSettings
from core.simulator import compute_exhaust_valve_area


def test_exhaust_valve_area_wrap_uses_camshaft_get_lift() -> None:
    cam = Camshaft(exhaust_lift=10.0, exhaust_duration=280.0, lobe_separation=110.0, advance=0.0)
    head = CylinderHead(exhaust_valves=2, exhaust_valve_seat_diameter_mm=30.0)
    settings = SimulationSettings(exhaust_valve_area_model="curtain")

    area_wrap = compute_exhaust_valve_area(5.0, cam, head, settings)
    area_closed = compute_exhaust_valve_area(400.0, cam, head, settings)

    assert area_wrap > 0.0
    assert area_closed == 0.0
