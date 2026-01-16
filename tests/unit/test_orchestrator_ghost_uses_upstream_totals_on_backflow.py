from typing import Optional

import pytest

np = pytest.importorskip("numpy")

import numpy as np

import core.advanced.orchestrator as orchestrator_module
from core.advanced.state import stagnation_from_static
from core.advanced.coupling import ValveTiming


def test_orchestrator_ghost_uses_upstream_totals_on_backflow(monkeypatch: pytest.MonkeyPatch) -> None:
    p_pipe = 180000.0
    T_pipe = 650.0
    Y_pipe = 0.85
    captured: dict[str, float] = {}

    class _Stop(Exception):
        pass

    u_pipe = 120.0
    expected_p0, expected_T0 = stagnation_from_static(
        p_pipe, T_pipe, u_pipe, orchestrator_module.OrchestratorConfig().gamma, orchestrator_module.OrchestratorConfig().gas_constant
    )

    def fake_conserved_to_primitive(U: np.ndarray, gamma: float, gas_constant: float) -> np.ndarray:
        prim = np.zeros((U.shape[0], 5))
        prim[:, 0] = 1.0
        prim[:, 1] = u_pipe
        prim[:, 2] = p_pipe
        prim[:, 3] = T_pipe
        prim[:, 4] = Y_pipe
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
        cp_model: str = "constant",
        p0_down=None,
        T0_down=None,
        Y0_down=None,
        loss_coeff: float = 0.0,
        rho_down: Optional[float] = None,
        u_down: Optional[float] = None,
        area_pipe_m2: Optional[float] = None,
    ) -> tuple[float, float, float, float]:
        return -0.1, -1.0, -0.01, valve.area_eff(angle_deg)

    def fake_ghost_state(
        p0: float,
        T0: float,
        Y0: float,
        mdot: float,
        area_face: float,
        gamma: float,
        gas_constant: float,
        phase: str = "phase2",
        cp_model: str = "constant",
    ) -> np.ndarray:
        captured["p0"] = p0
        captured["T0"] = T0
        captured["Y0"] = Y0
        raise _Stop()

    def fake_step(
        U: np.ndarray,
        dx: float,
        dt: float,
        gamma: float,
        gas_constant: float,
        friction_factor: float = 0.0,
        diameter: float = 1.0,
        p_outlet: float | None = None,
        outlet_mode: str | None = None,
        reflection_coeff: float | None = None,
        impedance: float | None = None,
        friction_model: str | None = None,
        roughness: float = 0.0,
        mu: float = 1.8e-5,
        friction_energy_mode: str = "wall_loss",
        use_numba_1d: bool = False,
    ) -> np.ndarray:
        return U

    def fake_cfl_dt(
        U: np.ndarray,
        dx: float,
        gamma: float,
        gas_constant: float,
        cfl: float,
        dt_max: float,
        ghost_left: int = 0,
        ghost_right: int = 0,
    ) -> float:
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

    assert pytest.approx(expected_p0, rel=1e-9, abs=1e-6) == captured.get("p0")
    assert pytest.approx(expected_T0, rel=1e-9, abs=1e-6) == captured.get("T0")
    assert pytest.approx(Y_pipe, rel=0.0, abs=1e-9) == captured.get("Y0")
