from __future__ import annotations

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@pytest.mark.integration
def test_turbo_response_model_delays_low_rpm_boost_build() -> None:
    engine = Engine()
    turbo_cfg = {
        "enabled": True,
        "target_boost_kpa": 60.0,
        "compressor_map": [
            {"flow_kg_s": 0.03, "pr": 1.4},
            {"flow_kg_s": 0.08, "pr": 1.9},
        ],
        "turbine_map": [
            {"flow_kg_s": 0.03, "pr": 1.3},
            {"flow_kg_s": 0.08, "pr": 1.7},
        ],
        "response_model": {
            "enabled": True,
            "spool_rpm": 4200.0,
            "spool_width_rpm": 700.0,
            "flow_ref_kg_s": 0.18,
            "flow_width_kg_s": 0.05,
            "min_response": 0.2,
        },
    }

    turbo_engine = Engine.from_dict(engine.to_dict())
    turbo_engine.turbo = turbo_engine.turbo.from_dict(turbo_cfg)
    turbo_cycle_low = CylinderSimulator(turbo_engine).run_cycle(2000.0)
    turbo_cycle_high = CylinderSimulator(turbo_engine).run_cycle(6000.0)

    no_response_engine = Engine.from_dict(engine.to_dict())
    no_response_cfg = dict(turbo_cfg)
    no_response_cfg["response_model"] = {}
    no_response_engine.turbo = no_response_engine.turbo.from_dict(no_response_cfg)
    no_response_low = CylinderSimulator(no_response_engine).run_cycle(2000.0)

    assert turbo_cycle_low["boost_kpa"] < no_response_low["boost_kpa"]
    assert turbo_cycle_high["boost_kpa"] > turbo_cycle_low["boost_kpa"]
    assert turbo_cycle_low["turbo_response"]["enabled"] is True
    assert turbo_cycle_low["turbo_response"]["response_factor"] < turbo_cycle_high["turbo_response"]["response_factor"]

