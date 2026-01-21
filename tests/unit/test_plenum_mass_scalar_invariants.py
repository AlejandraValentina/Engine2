import math

from core.advanced.nozzle import nozzle_mass_flow
from core.advanced.plenum_cv import IntakePlenumConfig, PlenumControlVolume


def test_plenum_mass_scalar_invariants() -> None:
    gamma = 1.35
    gas_constant = 287.0
    cp = gamma * gas_constant / (gamma - 1.0)

    cfg = IntakePlenumConfig(enabled=True, volume_m3=0.003, p_init_pa=101325.0, t_init_k=300.0, y_init=1.0)
    plenum = PlenumControlVolume(cfg, gas_constant, cp, gamma)

    p_amb = 101325.0
    T_amb = 300.0
    Y_amb = 1.0
    Y_pipe = 0.0
    area_throttle = 0.002
    area_pipe = 0.001
    dt = 0.005

    pipe_pressures = [90000.0] * 6 + [130000.0] * 4 + [95000.0] * 6
    tol = 1e-6
    for p_pipe in pipe_pressures:
        mdot_throttle, Hdot_throttle, Ydot_throttle = nozzle_mass_flow(
            p_amb,
            T_amb,
            plenum.p,
            area_throttle,
            gamma,
            gas_constant,
            cp,
            Y_amb,
            p0_down=plenum.p,
            T0_down=plenum.T,
            Y0_down=plenum.Y,
        )
        mdot_pipe, Hdot_pipe, Ydot_pipe = nozzle_mass_flow(
            plenum.p,
            plenum.T,
            p_pipe,
            area_pipe,
            gamma,
            gas_constant,
            cp,
            plenum.Y,
            p0_down=p_pipe,
            T0_down=T_amb,
            Y0_down=Y_pipe,
        )
        plenum.update(dt, mdot_throttle, Hdot_throttle, Ydot_throttle, mdot_pipe, Hdot_pipe, Ydot_pipe)

        assert math.isfinite(plenum.m_total)
        assert math.isfinite(plenum.p)
        assert math.isfinite(plenum.T)
        assert plenum.m_total > 0.0
        assert 0.0 <= plenum.Y <= 1.0
        assert plenum.p + tol >= cfg.p_floor_pa
        assert plenum.T + tol >= cfg.t_floor_k
