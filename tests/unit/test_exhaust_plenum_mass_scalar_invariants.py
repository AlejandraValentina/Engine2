import math

from core.advanced.nozzle import nozzle_mass_flow
from core.advanced.plenum_cv import ExhaustPlenumConfig, PlenumControlVolume


def test_exhaust_plenum_mass_scalar_invariants() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)

    cfg = ExhaustPlenumConfig(enabled=True, volume_m3=0.003, p_init_pa=101325.0, t_init_k=700.0, y_init=0.0)
    plenum = PlenumControlVolume(cfg, gas_constant, cp, gamma)

    p_pipe = 101325.0
    T_pipe = 700.0
    Y_pipe = 1.0
    T_cyl = 900.0
    Y_cyl = 0.0
    area_valve = 0.0015
    area_pipe = 0.001
    dt = 0.001
    tol = 1e-6

    cyl_pressures = [180000.0] * 6 + [120000.0] * 4 + [95000.0] * 6
    pipe_pressures = [101325.0, 125000.0, 90000.0, 110000.0] * 4

    for p_cyl, p_pipe_step in zip(cyl_pressures, pipe_pressures):
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
            p_pipe_step,
            area_pipe,
            gamma,
            gas_constant,
            cp,
            plenum.Y,
            p0_down=p_pipe_step,
            T0_down=T_pipe,
            Y0_down=Y_pipe,
        )
        plenum.update(dt, mdot_valve, Hdot_valve, Ydot_valve, mdot_plenum, Hdot_plenum, Ydot_plenum)

        assert math.isfinite(plenum.m_total)
        assert math.isfinite(plenum.p)
        assert math.isfinite(plenum.T)
        assert plenum.m_total > 0.0
        assert 0.0 <= plenum.Y <= 1.0
        assert plenum.p + tol >= cfg.p_floor_pa
        assert plenum.T + tol >= cfg.t_floor_k
