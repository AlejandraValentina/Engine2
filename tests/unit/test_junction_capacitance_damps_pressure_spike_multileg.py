import math

from core.advanced.junctions import JunctionCapacitance, JunctionCapacitanceConfig, JunctionFlow, mix_junction_totals


def test_junction_capacitance_damps_pressure_spike_multileg() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    cfg = JunctionCapacitanceConfig(enabled=True, volume_m3=0.05)
    junction = JunctionCapacitance(
        cfg,
        gamma,
        gas_constant,
        cp,
        p_init=101325.0,
        T_init=500.0,
        Y_init=0.1,
    )

    pulses = [200000.0, 120000.0, 200000.0, 120000.0]
    dt = 0.01
    p0_cap = []
    p0_mix = []
    for p0_in in pulses:
        inflows = [
            JunctionFlow(mdot=0.05, p0=p0_in, T0=700.0, Y0=0.2),
            JunctionFlow(mdot=0.03, p0=120000.0, T0=600.0, Y0=0.1),
            JunctionFlow(mdot=0.02, p0=110000.0, T0=550.0, Y0=0.1),
        ]
        p0_j, T0_j, Y_j = junction.totals()
        outflows = [
            JunctionFlow(mdot=sum(flow.mdot for flow in inflows), p0=p0_j, T0=T0_j, Y0=Y_j)
        ]
        junction.update(dt, inflows, outflows)
        p0_cap.append(junction.totals()[0])
        p0_mix.append(mix_junction_totals(inflows, cp)[0])

    amp_cap = max(p0_cap) - min(p0_cap)
    amp_mix = max(p0_mix) - min(p0_mix)
    assert math.isfinite(amp_cap)
    assert amp_cap < amp_mix * 0.8
