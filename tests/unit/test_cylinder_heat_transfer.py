import copy

from core.advanced.cylinder_cv import CylinderControlVolume, HeatTransferConfig


def _build_cylinder(heat: HeatTransferConfig) -> CylinderControlVolume:
    return CylinderControlVolume(
        m_total=0.001,
        m_fresh=0.001,
        T=800.0,
        p=150000.0,
        V=1e-4,
        gamma=1.35,
        gas_constant=287.0,
        heat_transfer=heat,
    )


def test_heat_transfer_disabled_no_effect() -> None:
    base = _build_cylinder(HeatTransferConfig(enabled=False))
    with_area = copy.deepcopy(base)
    with_area.update(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, A_wet=0.1)
    no_area = copy.deepcopy(base)
    no_area.update(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert with_area.T == no_area.T
    assert with_area.p == no_area.p
    assert with_area.m_total == no_area.m_total


def test_heat_transfer_removes_energy_when_gas_hotter() -> None:
    heat = HeatTransferConfig(enabled=True, model="constant_h", h_const=300.0, wall_temp_K=400.0)
    cyl_ht = _build_cylinder(heat)
    cyl_no = _build_cylinder(HeatTransferConfig(enabled=False))
    cyl_ht.update(0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, A_wet=0.1)
    cyl_no.update(0.01, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, A_wet=0.1)
    assert cyl_ht.T < cyl_no.T
