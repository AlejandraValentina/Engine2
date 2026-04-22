import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def _make_engine(throttle_cfm: float) -> Engine:
    engine = Engine()
    engine.intake.throttle_cfm = throttle_cfm
    engine.head.port_flow_cfm = 250.0
    engine.head.port_flow_efficiency = 0.9
    return engine


def test_flow_cap_does_not_limit_when_supply_high():
    engine = _make_engine(throttle_cfm=2000.0)
    sim = CylinderSimulator(engine)
    res = sim.run_cycle(3000.0)
    assert res["ve_actual"] > 0.2


def test_flow_cap_scales_with_throttle_capacity():
    engine_high = _make_engine(throttle_cfm=2000.0)
    sim_high = CylinderSimulator(engine_high)
    res_high = sim_high.run_cycle(3000.0)

    engine_low = _make_engine(throttle_cfm=20.0)
    sim_low = CylinderSimulator(engine_low)
    res_low = sim_low.run_cycle(3000.0)

    assert res_low["ve_actual"] < res_high["ve_actual"]
    assert res_low["airflow_cfm"] <= engine_low.intake.throttle_cfm * 1.05
