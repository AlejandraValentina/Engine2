from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import numpy as np

from core.engine_components import Engine, Pipe
from core.simulator import Engine1DSolver
from core.thermo import CylinderSimulator
from core.wave_utils import build_exhaust_coupling, compute_pressure_matrix


def _build_solver(engine: Engine, target_dx: float = 0.05) -> Engine1DSolver:
    exhaust = engine.exhaust
    n_cyl = max(engine.block.num_cylinders, 1)
    primaries = [
        Pipe(
            length=exhaust.header_primary_length,
            diameter_inlet=exhaust.header_primary_diameter,
            diameter_outlet=exhaust.header_primary_diameter,
        )
        for _ in range(n_cyl)
    ]
    tail_dia = exhaust.header_primary_diameter * max(np.sqrt(n_cyl) * 0.6, 1.2)
    tailpipe = Pipe(
        length=exhaust.collector_length,
        diameter_inlet=tail_dia,
        diameter_outlet=tail_dia,
    )
    return Engine1DSolver(
        primaries,
        tailpipe,
        engine.block.firing_order,
        settings=engine.simulation_settings,
        camshaft=engine.camshaft,
        head=engine.head,
        target_dx=target_dx,
    )


@pytest.mark.integration
@pytest.mark.slow
def test_0d_to_1d_scope_signal() -> None:
    engine = Engine.load_from_file("presets/legacy/custom_twin_230cc.json")
    engine.simulation_settings.enable_0d_to_1d_exhaust_coupling = True
    rpm = 2000.0

    cycle = CylinderSimulator(engine).run_cycle(rpm)
    coupling = build_exhaust_coupling(
        cycle["angle"],
        cycle["exhaust_p_stag"],
        cycle["exhaust_t_stag"],
        engine.block.firing_order,
    )

    solver = _build_solver(engine, target_dx=0.05)
    max_steps = 60
    history: list[np.ndarray] = []
    for _ in range(max_steps):
        dt = solver.get_time_step()
        base_angle = (solver.time * rpm * 6.0) % 720.0
        p_stag_by_cyl: dict[int, float] = {}
        t_stag_by_cyl: dict[int, float] = {}
        for cyl_id in range(1, solver.n_cyl + 1):
            data = coupling.get(cyl_id)
            if data is None:
                raise ValueError(f"Missing coupling data for cylinder {cyl_id}")
            cyl_angle = (base_angle + solver.phase_map.get(cyl_id, 0.0)) % 720.0
            p_stag_by_cyl[cyl_id] = float(np.interp(cyl_angle, data["angle"], data["p_stag"]))
            t_stag_by_cyl[cyl_id] = float(np.interp(cyl_angle, data["angle"], data["t_stag"]))
        solver.step(rpm=rpm, dt=dt, p_stag_by_cyl=p_stag_by_cyl, T_stag_by_cyl=t_stag_by_cyl)
        history.append(solver.primary_states[0]["U"].copy())
    matrix = compute_pressure_matrix(history, solver.gamma)

    assert np.isfinite(matrix).all(), "Non-finite pressures in scope matrix"
    span = float(matrix.max() - matrix.min())
    assert span > 0.0, f"Expected pressure variation, span={span:.3e} Pa"
