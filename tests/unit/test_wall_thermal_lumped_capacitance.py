from core.advanced.wall_thermal import init_wall_temperature, wall_thermal_step
from core.engine_components import WallThermalConfig


def test_wall_thermal_moves_toward_gas_temp() -> None:
    cfg = WallThermalConfig(
        enabled=True,
        m_wall_kg=2.0,
        cp_wall_j_per_kgk=1000.0,
        h_w_per_m2k=150.0,
        area_m2=0.5,
        twall_init_k=300.0,
        twall_min_k=200.0,
        twall_max_k=800.0,
    )
    twall = init_wall_temperature(cfg)
    temps = []
    for _ in range(6):
        twall, _ = wall_thermal_step(twall, 600.0, 0.1, cfg)
        temps.append(twall)

    assert temps[0] > cfg.twall_init_k
    assert all(temps[i] <= temps[i + 1] for i in range(len(temps) - 1))
    assert temps[-1] <= 600.0


def test_wall_thermal_disabled_no_change() -> None:
    cfg = WallThermalConfig(
        enabled=False,
        m_wall_kg=1.0,
        cp_wall_j_per_kgk=1000.0,
        h_w_per_m2k=100.0,
        area_m2=1.0,
        twall_init_k=350.0,
        twall_min_k=250.0,
        twall_max_k=900.0,
    )
    twall = init_wall_temperature(cfg)
    twall_next, qdot = wall_thermal_step(twall, 800.0, 0.25, cfg)

    assert twall_next == twall
    assert qdot == 0.0
