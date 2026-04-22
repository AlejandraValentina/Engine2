import math

import pytest

from core.advanced.junctions import JunctionCapacitance, JunctionCapacitanceConfig, JunctionFlow, mix_junction_totals


def test_junction_capacitance_conserves_mass_scalar() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    config = JunctionCapacitanceConfig(enabled=True, volume_m3=0.01)
    junction = JunctionCapacitance(
        config,
        gamma,
        gas_constant,
        cp,
        p_init=120000.0,
        T_init=400.0,
        Y_init=0.2,
    )

    m0 = junction.m_total
    mY0 = junction.mY
    inflows = [JunctionFlow(mdot=0.2, p0=150000.0, T0=600.0, Y0=0.9)]
    outflows = [JunctionFlow(mdot=0.1, p0=130000.0, T0=500.0, Y0=0.1)]
    dt = 0.1

    junction.update(dt, inflows, outflows)

    expected_m = m0 + (0.2 - 0.1) * dt
    expected_mY = mY0 + (0.2 * 0.9 - 0.1 * 0.1) * dt
    expected_Y = expected_mY / expected_m

    assert math.isfinite(junction.m_total)
    assert math.isfinite(junction.mY)
    assert abs(junction.m_total - expected_m) < 1e-6
    assert abs(junction.mY / junction.m_total - expected_Y) < 1e-6
    assert 0.0 <= junction.Y <= 1.0


def test_junction_capacitance_damps_pressure_peaks_vs_algebraic() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    config = JunctionCapacitanceConfig(enabled=True, volume_m3=0.05)
    junction = JunctionCapacitance(
        config,
        gamma,
        gas_constant,
        cp,
        p_init=101325.0,
        T_init=500.0,
        Y_init=0.1,
    )

    pulses = [
        (200000.0, 700.0),
        (120000.0, 550.0),
        (200000.0, 700.0),
        (120000.0, 550.0),
    ]
    dt = 0.01
    p0_cap = []
    p0_mix = []
    for p0_in, T0_in in pulses:
        inflows = [JunctionFlow(mdot=0.05, p0=p0_in, T0=T0_in, Y0=0.2)]
        p0_j, T0_j, Y_j = junction.totals()
        outflows = [JunctionFlow(mdot=0.05, p0=p0_j, T0=T0_j, Y0=Y_j)]
        junction.update(dt, inflows, outflows)
        p0_cap.append(junction.totals()[0])
        p0_mix.append(mix_junction_totals(inflows, cp)[0])

    amp_cap = max(p0_cap) - min(p0_cap)
    amp_mix = max(p0_mix) - min(p0_mix)
    assert amp_cap < amp_mix * 0.8
