import copy

import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator
from tests._assertions import assert_bmep_consistency, assert_hp_tq_consistency


@pytest.mark.parametrize("rpm", [1500.0, 3000.0, 6000.0, 8000.0])
def test_power_torque_identities(rpm, k20_config):
    engine = Engine.from_dict(copy.deepcopy(k20_config))
    sim = CylinderSimulator(engine)
    results = sim.run_cycle(rpm)
    hp = results["mean_power_hp"]
    tq = results["mean_torque_nm"]
    bmep = results.get("bmep_bar")
    ve_val = results.get("ve")

    bmep_str = f"{bmep:.3f}" if bmep is not None else "n/a"
    ve_str = f"{ve_val:.2f}" if ve_val is not None else "n/a"
    print(f"RPM={rpm:.0f} hp={hp:.2f} tq={tq:.2f} bmep={bmep_str} ve={ve_str}")

    assert_hp_tq_consistency(hp, tq, rpm)
    if bmep is not None:
        assert_bmep_consistency(bmep, tq, engine.block.displacement_cc)
