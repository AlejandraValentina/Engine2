from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from core.wave_utils import mass_flow_nozzle


def test_mass_flow_choking_behavior() -> None:
    p_up = 200000.0
    t_up = 800.0
    area = 1e-4
    gamma = 1.33
    gas_constant = 287.0

    mdot_high, t_exit_high, _ = mass_flow_nozzle(p_up, t_up, 180000.0, area, gamma, gas_constant, cd=1.0)
    mdot_low, t_exit_low, _ = mass_flow_nozzle(p_up, t_up, 20000.0, area, gamma, gas_constant, cd=1.0)

    assert mdot_low > mdot_high
    assert t_exit_low < t_exit_high
