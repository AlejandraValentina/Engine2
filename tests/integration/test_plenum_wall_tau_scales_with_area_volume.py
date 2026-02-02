import pytest

from core.advanced.plenum_cv import (
    IntakePlenumConfig,
    PlenumControlVolume,
    PlenumWallThermalConfig,
)


@pytest.mark.integration
def test_plenum_wall_tau_scales_with_area_volume() -> None:
    cfg_small = IntakePlenumConfig(
        enabled=True,
        volume_m3=0.01,
        p_init_pa=101325.0,
        t_init_k=600.0,
    )
    cfg_small.wall_thermal = PlenumWallThermalConfig(
        enabled=True,
        area_m2=0.2,
        twall_init_k=300.0,
        h_model="dittus_boelter",
    )

    cfg_large = IntakePlenumConfig(
        enabled=True,
        volume_m3=0.01,
        p_init_pa=101325.0,
        t_init_k=600.0,
    )
    cfg_large.wall_thermal = PlenumWallThermalConfig(
        enabled=True,
        area_m2=0.4,
        twall_init_k=300.0,
        h_model="dittus_boelter",
    )

    plenum_small = PlenumControlVolume(cfg_small, gas_constant=287.0, cp=1005.0, gamma=1.4)
    plenum_large = PlenumControlVolume(cfg_large, gas_constant=287.0, cp=1005.0, gamma=1.4)

    t0_small = plenum_small.T
    t0_large = plenum_large.T

    plenum_small.update(
        dt=0.05,
        mdot_throttle=0.0,
        Hdot_throttle=0.0,
        Ydot_throttle=0.0,
        mdot_pipe=0.0,
        Hdot_pipe=0.0,
        Ydot_pipe=0.0,
    )
    plenum_large.update(
        dt=0.05,
        mdot_throttle=0.0,
        Hdot_throttle=0.0,
        Ydot_throttle=0.0,
        mdot_pipe=0.0,
        Hdot_pipe=0.0,
        Ydot_pipe=0.0,
    )

    drop_small = t0_small - plenum_small.T
    drop_large = t0_large - plenum_large.T

    assert drop_large > drop_small
