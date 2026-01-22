import math

from core.advanced.junctions import JunctionCapacitance, JunctionCapacitanceConfig, JunctionFlow


def test_junction_capacitance_conserves_mass_scalar() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    cfg = JunctionCapacitanceConfig(enabled=True, volume_m3=0.02)
    junction = JunctionCapacitance(
        cfg,
        gamma,
        gas_constant,
        cp,
        p_init=101325.0,
        T_init=600.0,
        Y_init=0.05,
    )

    dt = 0.02
    inflow_sets = [
        [
            JunctionFlow(mdot=0.05, p0=150000.0, T0=700.0, Y0=0.1),
            JunctionFlow(mdot=0.03, p0=120000.0, T0=650.0, Y0=0.0),
        ],
        [
            JunctionFlow(mdot=0.02, p0=130000.0, T0=680.0, Y0=0.2),
            JunctionFlow(mdot=0.01, p0=110000.0, T0=620.0, Y0=0.0),
        ],
    ]
    outflow_sets = [
        [JunctionFlow(mdot=0.04, p0=120000.0, T0=620.0, Y0=0.1)],
        [JunctionFlow(mdot=0.05, p0=115000.0, T0=610.0, Y0=0.1)],
    ]

    for inflows, outflows in zip(inflow_sets, outflow_sets):
        junction.update(dt, inflows, outflows)
        assert math.isfinite(junction.m_total)
        assert math.isfinite(junction.mY)
        assert math.isfinite(junction.p)
        assert math.isfinite(junction.T)
        assert junction.m_total > 0.0
        assert 0.0 <= junction.Y <= 1.0
