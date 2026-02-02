import math

import pytest

from core.advanced.plenum_cv import (
    IntakePlenumConfig,
    PlenumAmbientLossConfig,
    PlenumControlVolume,
    PlenumWallThermalConfig,
    _plenum_wall_area,
    _plenum_wall_mass,
)


def test_plenum_wall_energy_conservation_no_ambient_loss() -> None:
    cfg = IntakePlenumConfig(
        enabled=True,
        volume_m3=0.01,
        p_init_pa=101325.0,
        t_init_k=600.0,
    )
    cfg.wall_thermal = PlenumWallThermalConfig(
        enabled=True,
        material_rho_kg_m3=7800.0,
        material_cp_j_per_kgk=500.0,
        thickness_m=0.003,
        twall_init_k=300.0,
        h_model="dittus_boelter",
        ambient_loss=PlenumAmbientLossConfig(enabled=False),
    )

    plenum = PlenumControlVolume(cfg, gas_constant=287.0, cp=1005.0, gamma=1.4)
    area = _plenum_wall_area(cfg, plenum.volume_m3)
    m_wall = _plenum_wall_mass(cfg, area)
    e_before = plenum.E_total + m_wall * cfg.wall_thermal.material_cp_j_per_kgk * plenum.state.T_wall

    plenum.update(
        dt=0.05,
        mdot_throttle=0.0,
        Hdot_throttle=0.0,
        Ydot_throttle=0.0,
        mdot_pipe=0.0,
        Hdot_pipe=0.0,
        Ydot_pipe=0.0,
    )

    e_after = plenum.E_total + m_wall * cfg.wall_thermal.material_cp_j_per_kgk * plenum.state.T_wall
    assert math.isfinite(e_after)
    assert e_after == pytest.approx(e_before, rel=1e-6, abs=1e-3)
