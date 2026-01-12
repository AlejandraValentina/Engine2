import pytest

np = pytest.importorskip("numpy")

import numpy as np

import core.advanced.orchestrator as orchestrator_module
from core.advanced.coupling import ValveTiming


def test_orchestrator_wires_friction(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class _Stop(Exception):
        pass

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
        p0_down=None,
        T0_down=None,
        Y0_down=None,
        loss_coeff: float = 0.0,
        rho_down=None,
        u_down=None,
    ) -> tuple[float, float, float, float]:
        return 0.0, 0.0, 0.0, valve.area_eff(angle_deg)

    def fake_ghost_state(
        p0: float,
        T0: float,
        Y0: float,
        mdot: float,
        area_face: float,
        gamma: float,
        gas_constant: float,
        phase: str = "phase2",
    ) -> np.ndarray:
        return np.array([1.2, 0.0, 1.0, 0.2])

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
    ) -> np.ndarray:
        captured["friction_model"] = friction_model
        captured["roughness"] = roughness
        captured["mu"] = mu
        raise _Stop()

    def fake_cfl_dt(U: np.ndarray, dx: float, gamma: float, gas_constant: float, cfl: float, dt_max: float) -> float:
        return dt_max

    monkeypatch.setattr(orchestrator_module, "boundary_flux_from_nozzle", fake_boundary_flux)
    monkeypatch.setattr(orchestrator_module, "ghost_state_from_nozzle", fake_ghost_state)
    monkeypatch.setattr(orchestrator_module, "muscl_hancock_step", fake_step)
    monkeypatch.setattr(orchestrator_module, "cfl_dt", fake_cfl_dt)

    cfg = orchestrator_module.OrchestratorConfig(
        max_cycles=1,
        dt_max=1e-4,
        enable_friction=True,
        roughness_m=1e-5,
        mu=2.1e-5,
    )
    orchestrator = orchestrator_module.Orchestrator(cfg)
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

    assert captured["friction_model"] == "swamee-jain"
    assert captured["roughness"] == pytest.approx(1e-5, rel=0.0, abs=1e-12)
    assert captured["mu"] == pytest.approx(2.1e-5, rel=0.0, abs=1e-12)
