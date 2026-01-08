from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from core.engine_components import Camshaft, CylinderHead, SimulationSettings
from core.simulator import compute_exhaust_valve_area
from core.wave_utils import mass_flow_nozzle


def test_cd_applied_once() -> None:
    cam = Camshaft(exhaust_lift=10.0)
    head = CylinderHead(exhaust_valves=1, exhaust_valve_seat_diameter_mm=30.0)
    settings_low = SimulationSettings(exhaust_valve_area_model="curtain", exhaust_valve_cd=0.5)
    settings_high = SimulationSettings(exhaust_valve_area_model="curtain", exhaust_valve_cd=1.0)

    center = 720.0 - (cam.lobe_separation + cam.advance)
    area_low = compute_exhaust_valve_area(center, cam, head, settings_low)
    area_high = compute_exhaust_valve_area(center, cam, head, settings_high)

    assert area_low == area_high

    mdot_low, _, _ = mass_flow_nozzle(
        200000.0, 900.0, 100000.0, area_low, 1.35, 287.0, cd=0.5
    )
    mdot_high, _, _ = mass_flow_nozzle(
        200000.0, 900.0, 100000.0, area_high, 1.35, 287.0, cd=1.0
    )

    assert mdot_low == pytest.approx(0.5 * mdot_high, rel=1e-6)
