import copy

import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator

pytestmark = [pytest.mark.slow]


@pytest.mark.integration
@pytest.mark.parametrize("boost_bar", [0.7])
def test_boost_increases_power(boost_bar, k20_config):
    base_engine = Engine.from_dict(copy.deepcopy(k20_config))
    base_hp = CylinderSimulator(base_engine).run_cycle(6000.0)["mean_power_hp"]

    boosted_cfg = copy.deepcopy(k20_config)
    boosted_cfg["supercharger"] = {"type": "Turbo", "boost_pressure_bar": boost_bar}
    boosted_hp = CylinderSimulator(Engine.from_dict(boosted_cfg)).run_cycle(6000.0)["mean_power_hp"]

    print(f"Boost {boost_bar} bar -> base_hp={base_hp:.2f} boosted_hp={boosted_hp:.2f}")
    assert boosted_hp > base_hp * 1.25


@pytest.mark.integration
def test_intake_restriction_reduces_power(k20_config):
    base_hp = CylinderSimulator(Engine.from_dict(copy.deepcopy(k20_config))).run_cycle(8000.0)["mean_power_hp"]

    restricted_cfg = copy.deepcopy(k20_config)
    restricted_cfg["intake"] = {**restricted_cfg["intake"], "throttle_cfm": 300.0}
    restricted_hp = CylinderSimulator(Engine.from_dict(restricted_cfg)).run_cycle(8000.0)["mean_power_hp"]

    print(f"Throttle drop -> base_hp={base_hp:.2f} restricted_hp={restricted_hp:.2f}")
    assert restricted_hp <= base_hp * 0.90


@pytest.mark.integration
def test_friction_penalty_reduces_power(v10_config):
    race_hp = CylinderSimulator(Engine.from_dict(copy.deepcopy(v10_config))).run_cycle(8500.0)["mean_power_hp"]

    standard_cfg = copy.deepcopy(v10_config)
    standard_cfg["friction"] = {**standard_cfg.get("friction", {}), "bottom_end_type": "Standard"}
    standard_hp = CylinderSimulator(Engine.from_dict(standard_cfg)).run_cycle(8500.0)["mean_power_hp"]

    print(f"Friction switch -> race_hp={race_hp:.2f} standard_hp={standard_hp:.2f}")
    assert standard_hp <= race_hp * 0.95


@pytest.mark.integration
def test_valve_restriction_reduces_power(k20_config):
    base_hp = CylinderSimulator(Engine.from_dict(copy.deepcopy(k20_config))).run_cycle(8000.0)["mean_power_hp"]

    small_valves = copy.deepcopy(k20_config)
    small_head = {**small_valves["head"], "intake_valve_diameter": 20.0}
    small_valves["head"] = small_head
    restricted_hp = CylinderSimulator(Engine.from_dict(small_valves)).run_cycle(8000.0)["mean_power_hp"]

    print(f"Valve restriction -> base_hp={base_hp:.2f} restricted_hp={restricted_hp:.2f}")
    assert restricted_hp <= base_hp * 0.80
