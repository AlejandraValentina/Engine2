from core.advanced.cylinder_cv import CylinderControlVolume


def test_cylinder_cv_clamps_m_fresh_to_total() -> None:
    gamma = 1.35
    R = 287.0
    m_total = 1e-4
    T = 300.0
    V = 1e-4
    p = m_total * R * T / V

    cyl = CylinderControlVolume(
        m_total=m_total,
        m_fresh=m_total,
        T=T,
        p=p,
        V=V,
        gamma=gamma,
        gas_constant=R,
    )

    cyl.update(
        dt=0.01,
        mdot_in=0.0,
        Hdot_in=0.0,
        Ydot_in=1.0,
        mdot_out=0.0,
        Hdot_out=0.0,
        Ydot_out=0.0,
        Qdot_net=0.0,
        dVdt=0.0,
    )

    assert cyl.m_total > 0.0
    assert 0.0 <= cyl.m_fresh <= cyl.m_total
