import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def test_turbo_noop_when_disabled() -> None:
    engine = Engine()
    baseline = CylinderSimulator(engine).run_cycle(3000.0)["mean_power_hp"]

    engine_disabled = Engine()
    engine_disabled.turbo = engine_disabled.turbo.from_dict(
        {
            "enabled": False,
            "target_boost_kpa": 80.0,
            "compressor_map": [{"flow_kg_s": 0.05, "pr": 1.8}],
        }
    )
    disabled = CylinderSimulator(engine_disabled).run_cycle(3000.0)["mean_power_hp"]

    assert disabled == pytest.approx(baseline, rel=1e-12, abs=1e-12)
