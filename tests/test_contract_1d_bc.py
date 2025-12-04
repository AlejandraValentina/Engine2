import numpy as np
import pytest

from core import numerics
from core.model import Pipe
from core.simulator import Engine1DSolver


@pytest.mark.integration
@pytest.mark.parametrize("u_internal", [50.0, -50.0])
def test_outlet_boundary_constructs_ghost(u_internal: float):
    primary = Pipe(length=1.0, diameter_inlet=0.05, diameter_outlet=0.05, friction_coeff=0.02)
    tail = Pipe(length=0.5, diameter_inlet=0.06, diameter_outlet=0.06, friction_coeff=0.02)
    solver = Engine1DSolver([primary], tail, firing_order=[1], target_dx=0.05, p_atm=101325.0, T_amb=300.0)

    tail_state = solver.tail_state
    rho_i = float(tail_state["U"][-2, 0])
    p_i = solver.p_atm * 1.05  # perturb pressure to avoid trivial copy
    energy_density = p_i / (numerics.GAMMA - 1.0) / rho_i + 0.5 * u_internal * u_internal

    tail_state["U"][-2, 0] = rho_i
    tail_state["U"][-2, 1] = rho_i * u_internal
    tail_state["U"][-2, 2] = energy_density

    solver._tail_atmosphere()

    U_ghost = tail_state["U"][-1]
    rho_g, mom_g, energy_g = U_ghost
    u_g = mom_g / rho_g
    p_g = (numerics.GAMMA - 1.0) * (energy_g - 0.5 * rho_g * u_g * u_g)

    assert np.isfinite(U_ghost).all()
    assert rho_g > 0
    assert energy_g >= 0
    assert abs(p_g - solver.p_atm) / solver.p_atm < 0.05
    if u_internal < 0:
        T_ghost = p_g / (numerics.R * rho_g)
        assert pytest.approx(solver.T_amb, rel=0.1) == T_ghost
