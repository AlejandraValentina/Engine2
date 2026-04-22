import pytest

from core.advanced.wall_thermal import wall_thermal_step
from core.engine_components import WallThermalConfig


def _effective_h(qdot: float, area: float, T_gas: float, T_wall: float) -> float:
    return qdot / (area * (T_gas - T_wall))


def test_wall_thermal_h_model_constant_parity() -> None:
    cfg = WallThermalConfig(
        enabled=True,
        h_model="constant",
        h_w_per_m2k=200.0,
        area_m2=0.3,
        m_wall_kg=1.0,
        cp_wall_j_per_kgk=1000.0,
        twall_init_k=300.0,
        twall_min_k=200.0,
        twall_max_k=800.0,
    )
    twall, qdot = wall_thermal_step(300.0, 500.0, 0.1, cfg)
    expected_qdot = cfg.h_w_per_m2k * cfg.area_m2 * (500.0 - 300.0)

    assert twall > 300.0
    assert qdot == pytest.approx(expected_qdot)


def test_wall_thermal_dittus_boelter_increases_with_velocity() -> None:
    cfg = WallThermalConfig(
        enabled=True,
        h_model="dittus_boelter",
        h_w_per_m2k=50.0,
        area_m2=0.2,
        m_wall_kg=1.0,
        cp_wall_j_per_kgk=1000.0,
        twall_init_k=350.0,
        twall_min_k=200.0,
        twall_max_k=900.0,
    )
    T_gas = 600.0
    rho = 1.2
    diameter = 0.05

    _twall, qdot_lo = wall_thermal_step(
        350.0, T_gas, 0.05, cfg, rho=rho, u=20.0, diameter_m=diameter, cp=1005.0
    )
    _twall, qdot_hi = wall_thermal_step(
        350.0, T_gas, 0.05, cfg, rho=rho, u=80.0, diameter_m=diameter, cp=1005.0
    )

    h_lo = _effective_h(qdot_lo, cfg.area_m2, T_gas, 350.0)
    h_hi = _effective_h(qdot_hi, cfg.area_m2, T_gas, 350.0)

    assert h_hi > h_lo


def test_wall_thermal_clamps_applied() -> None:
    cfg_high = WallThermalConfig(
        enabled=True,
        h_model="constant",
        h_w_per_m2k=2000.0,
        h_mult=10.0,
        h_min=10.0,
        h_max=500.0,
        area_m2=0.4,
        m_wall_kg=1.0,
        cp_wall_j_per_kgk=1000.0,
        twall_init_k=300.0,
        twall_min_k=200.0,
        twall_max_k=800.0,
    )
    _twall, qdot_high = wall_thermal_step(300.0, 700.0, 0.1, cfg_high)
    h_eff_high = _effective_h(qdot_high, cfg_high.area_m2, 700.0, 300.0)

    cfg_low = WallThermalConfig(
        enabled=True,
        h_model="constant",
        h_w_per_m2k=5.0,
        h_mult=1.0,
        h_min=20.0,
        h_max=500.0,
        area_m2=0.4,
        m_wall_kg=1.0,
        cp_wall_j_per_kgk=1000.0,
        twall_init_k=300.0,
        twall_min_k=200.0,
        twall_max_k=800.0,
    )
    _twall, qdot_low = wall_thermal_step(300.0, 700.0, 0.1, cfg_low)
    h_eff_low = _effective_h(qdot_low, cfg_low.area_m2, 700.0, 300.0)

    assert h_eff_high == pytest.approx(cfg_high.h_max)
    assert h_eff_low == pytest.approx(cfg_low.h_min)


def test_wall_thermal_energy_sign() -> None:
    cfg = WallThermalConfig(
        enabled=True,
        h_model="constant",
        h_w_per_m2k=150.0,
        area_m2=0.2,
        m_wall_kg=1.0,
        cp_wall_j_per_kgk=1000.0,
        twall_init_k=300.0,
        twall_min_k=200.0,
        twall_max_k=800.0,
    )

    _twall, qdot_hot = wall_thermal_step(300.0, 600.0, 0.1, cfg)
    _twall, qdot_cold = wall_thermal_step(600.0, 300.0, 0.1, cfg)

    assert qdot_hot > 0.0
    assert qdot_cold < 0.0
