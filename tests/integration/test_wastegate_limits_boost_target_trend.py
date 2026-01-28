import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@pytest.mark.integration
def test_wastegate_limits_boost_target_trend() -> None:
    engine = Engine()
    base_cfg = {
        "enabled": True,
        "compressor_map": [
            {"flow_kg_s": 0.03, "pr": 1.5},
            {"flow_kg_s": 0.08, "pr": 2.0}
        ],
        "turbine_map": [
            {"flow_kg_s": 0.03, "pr": 1.3},
            {"flow_kg_s": 0.08, "pr": 1.8}
        ]
    }

    low_target = Engine.from_dict(engine.to_dict())
    cfg_low = dict(base_cfg)
    cfg_low["target_boost_kpa"] = 30.0
    low_target.turbo = low_target.turbo.from_dict(cfg_low)
    low_cycle = CylinderSimulator(low_target).run_cycle(3500.0)

    high_target = Engine.from_dict(engine.to_dict())
    cfg_high = dict(base_cfg)
    cfg_high["target_boost_kpa"] = 80.0
    high_target.turbo = high_target.turbo.from_dict(cfg_high)
    high_cycle = CylinderSimulator(high_target).run_cycle(3500.0)

    assert high_cycle["boost_kpa"] > low_cycle["boost_kpa"]
