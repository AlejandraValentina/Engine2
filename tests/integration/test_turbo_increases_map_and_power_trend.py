import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@pytest.mark.integration
def test_turbo_increases_map_and_power_trend() -> None:
    engine = Engine()
    baseline = CylinderSimulator(engine).run_cycle(4000.0)

    boosted = Engine.from_dict(engine.to_dict())
    boosted.turbo = boosted.turbo.from_dict(
        {
            "enabled": True,
            "target_boost_kpa": 60.0,
            "compressor_map": [
                {"flow_kg_s": 0.03, "pr": 1.4},
                {"flow_kg_s": 0.08, "pr": 1.9}
            ],
            "turbine_map": [
                {"flow_kg_s": 0.03, "pr": 1.3},
                {"flow_kg_s": 0.08, "pr": 1.7}
            ]
        }
    )
    boosted_cycle = CylinderSimulator(boosted).run_cycle(4000.0)

    assert boosted_cycle["mean_power_hp"] > baseline["mean_power_hp"]
    assert boosted_cycle.get("boost_kpa", 0.0) > 1.0
