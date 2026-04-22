import math

from core.advanced.nozzle import nozzle_mass_flow
from core.advanced.orchestrator import Throttle, _throttle_area_eff, _throttle_is_active


def test_throttle_wot_parity() -> None:
    cfg = Throttle(enabled=True, position=1.0, body_diam_m=0.07, cd=1.0, area_exponent=2.0)
    assert _throttle_is_active(cfg) is False
    area_eff = _throttle_area_eff(cfg)
    area_max = math.pi * (0.07 * 0.5) ** 2
    assert abs(area_eff - area_max) < 1e-12


def test_throttle_closed_blocks_flow() -> None:
    cfg = Throttle(enabled=True, position=0.0, body_diam_m=0.07, cd=1.0, area_exponent=2.0)
    area_eff = _throttle_area_eff(cfg)
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    mdot, Hdot, Ydot = nozzle_mass_flow(
        101325.0,
        300.0,
        95000.0,
        area_eff,
        gamma,
        gas_constant,
        cp,
        1.0,
    )
    assert mdot == 0.0
    assert Hdot == 0.0
    assert Ydot == 0.0


def test_throttle_monotonic_flow() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    p0 = 101325.0
    T0 = 300.0
    p_down = 95000.0
    pos_values = [1.0, 0.6, 0.3]
    mdots = []
    for pos in pos_values:
        cfg = Throttle(enabled=True, position=pos, body_diam_m=0.07, cd=1.0, area_exponent=2.0)
        area_eff = _throttle_area_eff(cfg)
        mdot, _, _ = nozzle_mass_flow(
            p0,
            T0,
            p_down,
            area_eff,
            gamma,
            gas_constant,
            cp,
            1.0,
        )
        mdots.append(mdot)

    assert mdots[0] > mdots[1] > mdots[2]


def test_throttle_backflow_direction_consistent() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    p0_amb = 101325.0
    T0_amb = 300.0
    p_down = 101000.0
    p0_pipe = 101600.0
    T0_pipe = 340.0
    area_eff = _throttle_area_eff(
        Throttle(enabled=True, position=0.7, body_diam_m=0.07, cd=1.0, area_exponent=2.0)
    )
    mdot, _, _ = nozzle_mass_flow(
        p0_amb,
        T0_amb,
        p_down,
        area_eff,
        gamma,
        gas_constant,
        cp,
        1.0,
        p0_down=p0_pipe,
        T0_down=T0_pipe,
        Y0_down=0.2,
    )
    assert mdot < 0.0
