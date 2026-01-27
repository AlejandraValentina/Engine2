"""Physics sanity checks for CylinderSimulator responses to tuning changes."""

import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def run_cycle_hp(engine: Engine, rpm: float) -> float:
    sim = CylinderSimulator(engine)
    res = sim.run_cycle(rpm)
    return float(res["mean_power_hp"])


def run_cycle_torque(engine: Engine, rpm: float):
    sim = CylinderSimulator(engine)
    res = sim.run_cycle(rpm)
    brake = float(res["mean_torque_nm"])
    friction = 15.0 + (rpm * 0.005) + (rpm ** 2 * 1e-6)
    indicated = brake + friction
    return brake, indicated


def test_turbo_boost_effect():
    engine = Engine()
    base_hp = run_cycle_hp(engine, 6000.0)

    engine_boosted = Engine.from_dict(engine.to_dict())
    engine_boosted.supercharger.type = "Turbo"
    engine_boosted.supercharger.boost_pressure_bar = 1.0
    boosted_hp = run_cycle_hp(engine_boosted, 6000.0)

    assert boosted_hp > base_hp * 1.5


def test_displacement_effect():
    engine = Engine()
    base_torque, _ = run_cycle_torque(engine, 6000.0)

    bigger = Engine.from_dict(engine.to_dict())
    bigger.block.stroke *= 1.2
    bigger_torque, _ = run_cycle_torque(bigger, 6000.0)

    assert bigger_torque > base_torque


def test_friction_model():
    engine = Engine()
    brake_low, ind_low = run_cycle_torque(engine, 2000.0)
    brake_high, ind_high = run_cycle_torque(engine, 8000.0)

    eff_low = brake_low / ind_low if ind_low > 0 else 0.0
    eff_high = brake_high / ind_high if ind_high > 0 else 0.0

    assert eff_high < eff_low


def test_intake_restriction():
    engine = Engine()
    engine.head.intake_valve_diameter = 50.0
    hp_huge = run_cycle_hp(engine, 7000.0)

    choked = Engine.from_dict(engine.to_dict())
    choked.head.intake_valve_diameter = 20.0
    hp_tiny = run_cycle_hp(choked, 7000.0)

    assert hp_tiny < hp_huge
