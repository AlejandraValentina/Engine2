from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import numpy as np

from core.engine_components import Pipe, SimulationSettings
from core.simulator import Engine1DSolver


def _build_solver(settings: SimulationSettings) -> Engine1DSolver:
    primary = Pipe(length=200.0, diameter_inlet=35.0, diameter_outlet=35.0)
    tail = Pipe(length=300.0, diameter_inlet=45.0, diameter_outlet=45.0)
    return Engine1DSolver([primary], tail, firing_order=[1], settings=settings)


def test_coupling_disabled_allows_default() -> None:
    settings = SimulationSettings(enable_0d_to_1d_exhaust_coupling=False)
    solver = _build_solver(settings)
    history, _, _ = solver.run_full_simulation(rpm=1000.0, cycles=1)
    assert len(history) > 0


def test_coupling_requires_inputs() -> None:
    settings = SimulationSettings(enable_0d_to_1d_exhaust_coupling=True)
    solver = _build_solver(settings)
    with pytest.raises(ValueError):
        solver.run_full_simulation(rpm=1000.0, cycles=1)

    angle = np.linspace(0.0, 720.0, 10)
    p_stag = np.full_like(angle, 200000.0)
    t_stag = np.full_like(angle, 900.0)
    coupling = {1: {"angle": angle, "p_stag": p_stag, "t_stag": t_stag}}

    history, _, _ = solver.run_full_simulation(rpm=1000.0, cycles=1, coupling_data=coupling)
    assert len(history) > 0
