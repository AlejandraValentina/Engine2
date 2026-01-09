from typing import Optional

import pytest

np = pytest.importorskip("numpy")

import numpy as np

import core.advanced.orchestrator as orchestrator_module
from core.advanced.coupling import ValveTiming


def test_orchestrator_uses_pipe_pressure_as_nozzle_downstream(monkeypatch: pytest.MonkeyPatch) -> None:
    target_p = 123456.0
    ghost_p = 223456.0
    captured: dict[str, float] = {}

    class _Stop(Exception):
        pass

    call_count = {"boundary": 0}
    ghost_marker = 9.0

    def fake_conserved_to_primitive(U: np.ndarray, gamma: float, gas_constant: float) -> np.ndarray:
        prim = np.zeros((U.shape[0], 5))
        prim[:, 0] = 1.0
        prim[:, 1] = 0.0
        prim[:, 2] = target_p if U[0, 0] != ghost_marker else ghost_p
        prim[:, 3] = 300.0
        prim[:, 4] = 0.0
        return prim

    def fake_boundary_flux(
        p0: float,
        T0: float,
        Y0: float,
        p_down: float,
        *,
        valve: ValveTiming,
        angle_deg: float,
        gamma: float,
        gas_constant: float,
        cp: float,
        p0_down: Optional[float] = None,
        T0_down: Optional[float] = None,
        Y0_down: Optional[float] = None,
    ) -> tuple[float, float, float, float]:
        call_count["boundary"] += 1
        if call_count["boundary"] >= 2:
            captured["p_down"] = p_down
            raise _Stop()
        return 0.1, 0.0, 0.0, valve.area_eff(angle_deg)

    def fake_ghost_state(
        p0: float,
        T0: float,
        Y0: float,
        mdot: float,
        area_face: float,
        gamma: float,
        gas_constant: float,
    ) -> np.ndarray:
        ghost = np.zeros(4)
        ghost[0] = ghost_marker
        ghost[1] = 0.0
        ghost[2] = 1.0
        ghost[3] = ghost_marker
        return ghost

    def fake_step(U: np.ndarray, dx: float, dt: float, gamma: float, gas_constant: float, friction_factor: float = 0.0, diameter: float = 1.0) -> np.ndarray:
        return U

    def fake_cfl_dt(U: np.ndarray, dx: float, gamma: float, gas_constant: float, cfl: float, dt_max: float) -> float:
        return dt_max

    monkeypatch.setattr(orchestrator_module, "conserved_to_primitive", fake_conserved_to_primitive)
    monkeypatch.setattr(orchestrator_module, "boundary_flux_from_nozzle", fake_boundary_flux)
    monkeypatch.setattr(orchestrator_module, "ghost_state_from_nozzle", fake_ghost_state)
    monkeypatch.setattr(orchestrator_module, "muscl_hancock_step", fake_step)
    monkeypatch.setattr(orchestrator_module, "cfl_dt", fake_cfl_dt)

    orchestrator = orchestrator_module.Orchestrator(orchestrator_module.OrchestratorConfig(max_cycles=1, dt_max=1e-4))
    valve = ValveTiming(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.0,
        seat_diameter_m=0.03,
        cd=1.0,
    )

    with pytest.raises(_Stop):
        orchestrator.run(
            rpm=2000.0,
            pipe_cells=2,
            pipe_length_m=0.2,
            pipe_diameter_m=0.05,
            bore_m=0.086,
            stroke_m=0.086,
            conrod_m=0.143,
            clearance_m3=1e-4,
            valve=valve,
        )

    assert pytest.approx(target_p, rel=0.0, abs=1e-9) == captured.get("p_down")
