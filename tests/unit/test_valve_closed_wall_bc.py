import numpy as np

from core.advanced.coupling import ValveTiming
from core.advanced.cylinder_cv import CylinderControlVolume
from core.advanced.orchestrator import OrchestratorConfig, ValveClosedWallBCConfig, _compute_valve_boundary
from core.advanced.state import Primitive1D, primitive_to_conserved


def test_valve_closed_wall_bc_reflective() -> None:
    cfg = OrchestratorConfig(
        valve_closed_wall_bc=ValveClosedWallBCConfig(enabled=True, area_eps_m2=1e-6)
    )
    valve = ValveTiming(
        open_start_deg=360.0,
        open_end_deg=540.0,
        max_lift_m=0.0,
        seat_diameter_m=0.03,
        cd=0.9,
    )
    prim_pipe = np.array([1.2, 15.0, 101325.0, 300.0, 0.2], dtype=float)
    cyl = CylinderControlVolume(
        m_total=0.001,
        m_fresh=0.001,
        T=300.0,
        p=101325.0,
        V=5e-5,
        gamma=cfg.gamma,
        gas_constant=cfg.gas_constant,
    )
    mdot, Hdot, Ydot, ghost = _compute_valve_boundary(
        cfg,
        valve,
        angle_deg=360.0,
        cyl=cyl,
        prim_pipe=prim_pipe,
        p0_pipe=101325.0,
        T0_pipe=300.0,
        Y_pipe=0.2,
        area_face=0.001,
        rho_pipe=prim_pipe[0],
        u_pipe=prim_pipe[1],
    )

    expected = primitive_to_conserved(
        Primitive1D(
            rho=prim_pipe[0],
            u=-prim_pipe[1],
            p=prim_pipe[2],
            T=prim_pipe[3],
            Y=prim_pipe[4],
        ),
        cfg.gamma,
        cfg.gas_constant,
    )
    assert mdot == 0.0
    assert Hdot == 0.0
    assert Ydot == 0.0
    assert abs(ghost[0] - expected.rho) < 1e-12
    assert abs(ghost[1] - expected.rhou) < 1e-12
    assert abs(ghost[3] - expected.rhoY) < 1e-12
