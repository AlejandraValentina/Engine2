import math

from core.advanced.junctions import JunctionCapacitanceConfig, JunctionFlow, junction_totals_from_flows, mix_junction_totals


def test_junction_capacitance_defaults_no_change() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)
    cfg = JunctionCapacitanceConfig(enabled=False, volume_m3=0.01)

    inflows = [
        JunctionFlow(mdot=0.04, p0=140000.0, T0=600.0, Y0=0.2),
        JunctionFlow(mdot=0.02, p0=120000.0, T0=500.0, Y0=0.1),
    ]
    outflows = []
    state, totals = junction_totals_from_flows(
        cfg,
        None,
        inflows,
        outflows,
        gas_constant=gas_constant,
        cp=cp,
        gamma=gamma,
        dt=0.01,
        p_init=101325.0,
        T_init=300.0,
        Y_init=0.0,
    )
    _ = state

    p_mix, T_mix, Y_mix = mix_junction_totals(inflows, cp)
    assert math.isclose(totals[0], p_mix, rel_tol=0.0, abs_tol=0.0)
    assert math.isclose(totals[1], T_mix, rel_tol=0.0, abs_tol=0.0)
    assert math.isclose(totals[2], Y_mix, rel_tol=0.0, abs_tol=0.0)
