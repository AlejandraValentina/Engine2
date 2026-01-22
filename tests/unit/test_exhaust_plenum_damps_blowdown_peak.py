import math

from core.advanced.nozzle import nozzle_mass_flow
from core.advanced.plenum_cv import ExhaustPlenumConfig, PlenumControlVolume


def test_exhaust_plenum_damps_blowdown_peak() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)

    cfg = ExhaustPlenumConfig(enabled=True, volume_m3=0.004, p_init_pa=101325.0, t_init_k=700.0, y_init=0.0)
    plenum = PlenumControlVolume(cfg, gas_constant, cp, gamma)

    p_pipe = 101325.0
    T_pipe = 700.0
    Y_pipe = 1.0
    T_cyl = 900.0
    Y_cyl = 0.0
    area_valve = 0.0015
    area_pipe = 0.001
    dt = 0.001

    cyl_pressures = [220000.0, 120000.0] * 12
    plenum_pressures = []
    for p_cyl in cyl_pressures:
        mdot_valve, Hdot_valve, Ydot_valve = nozzle_mass_flow(
            p_cyl,
            T_cyl,
            plenum.p,
            area_valve,
            gamma,
            gas_constant,
            cp,
            Y_cyl,
            p0_down=plenum.p,
            T0_down=plenum.T,
            Y0_down=plenum.Y,
        )
        mdot_plenum, Hdot_plenum, Ydot_plenum = nozzle_mass_flow(
            plenum.p,
            plenum.T,
            p_pipe,
            area_pipe,
            gamma,
            gas_constant,
            cp,
            plenum.Y,
            p0_down=p_pipe,
            T0_down=T_pipe,
            Y0_down=Y_pipe,
        )
        plenum.update(dt, mdot_valve, Hdot_valve, Ydot_valve, mdot_plenum, Hdot_plenum, Ydot_plenum)
        plenum_pressures.append(plenum.p)

    amp_cyl = max(cyl_pressures) - min(cyl_pressures)
    amp_plenum = max(plenum_pressures) - min(plenum_pressures)
    assert math.isfinite(amp_plenum)
    assert amp_plenum < amp_cyl * 0.8
