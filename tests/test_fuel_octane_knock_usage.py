from __future__ import annotations

import copy

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def test_octane_rating_changes_knock_result_in_model(k20_config) -> None:
    super_95 = copy.deepcopy(k20_config)
    premium_97 = copy.deepcopy(k20_config)

    super_95["fuel"]["type_name"] = "Gasoline"
    super_95["fuel"]["octane_rating"] = 95.0
    super_95["fuel"]["stoich_afr"] = 14.7

    premium_97["fuel"]["type_name"] = "Gasoline"
    premium_97["fuel"]["octane_rating"] = 97.0
    premium_97["fuel"]["stoich_afr"] = 14.7

    cycle_95 = CylinderSimulator(Engine.from_dict(super_95)).run_cycle(6000.0)
    cycle_97 = CylinderSimulator(Engine.from_dict(premium_97)).run_cycle(6000.0)

    assert bool(cycle_95["knock_warning"])
    assert cycle_95["knock_penalty_pct"] > 0.0
    assert not bool(cycle_97["knock_warning"])
    assert cycle_97["knock_penalty_pct"] == 0.0
    assert cycle_97["mean_power_hp"] > cycle_95["mean_power_hp"]
