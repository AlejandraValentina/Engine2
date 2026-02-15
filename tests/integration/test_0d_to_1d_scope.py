from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import numpy as np

from core.engine_components import Engine, Pipe
from core.simulator import Engine1DSolver
from core.thermo import CylinderSimulator
from core.wave_utils import build_exhaust_coupling, compute_pressure_matrix


def _build_solver(engine: Engine) -> Engine1DSolver:
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
    )


@pytest.mark.integration
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

    solver = _build_solver(engine)
    history, _, _ = solver.run_full_simulation(rpm=rpm, cycles=1, coupling_data=coupling)
    matrix = compute_pressure_matrix(history, solver.gamma)

    assert np.isfinite(matrix).all()
    assert float(matrix.max() - matrix.min()) > 0.0
