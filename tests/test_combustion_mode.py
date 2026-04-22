from __future__ import annotations

from core.engine_components import Engine
from pywavedyn.combustion_mode import apply_adaptive_combustion_mode


def test_apply_adaptive_combustion_mode_can_force_on_and_off() -> None:
    base = Engine()
    base.combustion.adaptive_model = {
        "enabled": False,
        "duration_scale": 1.05,
        "ca50_offset_deg": -1.0,
    }
    raw = base.to_dict()

    enabled_engine, enabled_raw, enabled_summary = apply_adaptive_combustion_mode(base, raw, mode="on")
    disabled_engine, disabled_raw, disabled_summary = apply_adaptive_combustion_mode(base, raw, mode="off")

    assert enabled_engine.combustion.adaptive_model["enabled"] is True
    assert enabled_raw["combustion"]["adaptive_model"]["enabled"] is True
    assert enabled_summary["adaptive_mode_requested"] == "on"
    assert enabled_summary["adaptive_enabled"] is True
    assert enabled_summary["adaptive_parameters"]["duration_scale"] == 1.05

    assert disabled_engine.combustion.adaptive_model["enabled"] is False
    assert disabled_raw["combustion"]["adaptive_model"]["enabled"] is False
    assert disabled_summary["adaptive_mode_requested"] == "off"
    assert disabled_summary["adaptive_enabled"] is False
