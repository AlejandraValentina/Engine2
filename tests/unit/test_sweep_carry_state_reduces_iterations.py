import pytest

np = pytest.importorskip("numpy")

import numpy as np

import core.advanced.orchestrator as orchestrator_module
from core.advanced.coupling import ValveTiming


def test_sweep_carry_state_reduces_iterations(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_init_pipe_state(
        cfg: orchestrator_module.OrchestratorConfig, pipe_cells: int
    ) -> tuple[np.ndarray, float, float, float, float]:
        U = np.full((pipe_cells + 2, 4), 1e-3, dtype=float)
        U[0] = U[1]
        U[-1] = U[-2]
        return U, 1e-3, 1.0, 1.0, 1.0

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
        rho_down=None,
        u_down=None,
        area_pipe_m2=None,
    ) -> tuple[float, float, float, float]:
        return 0.0, 0.0, 0.0, valve.area_eff(angle_deg)

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
        U_out = U.copy()
        U_out[1:-1] += 1.0
        return U_out

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

    def fake_qdot(*_args: object, **_kwargs: object) -> float:
        return 0.0

    monkeypatch.setattr(orchestrator_module, "_init_pipe_state", fake_init_pipe_state)
    monkeypatch.setattr(orchestrator_module, "boundary_flux_from_nozzle", fake_boundary_flux)
    monkeypatch.setattr(orchestrator_module, "muscl_hancock_step", fake_step)
    monkeypatch.setattr(orchestrator_module, "cfl_dt", fake_cfl_dt)
    monkeypatch.setattr(orchestrator_module, "combustion_qdot", fake_qdot)

    valve = ValveTiming(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.0,
        seat_diameter_m=0.03,
        cd=1.0,
    )

    base_cfg = dict(
        max_cycles=2,
        dt_max=1e-4,
        convergence_tol=0.0,
        periodicity_tol=0.0,
        periodicity_required=1,
    )
    sweep_base = dict(
        enabled=True,
        rpm_start=1000,
        rpm_end=1500,
        rpm_step=500,
        cycles_per_step=1,
    )

    cfg_carry = orchestrator_module.OrchestratorConfig(
        **base_cfg, sweep=orchestrator_module.SweepConfig(**{**sweep_base, "carry_state": True})
    )
    cfg_reset = orchestrator_module.OrchestratorConfig(
        **base_cfg, sweep=orchestrator_module.SweepConfig(**{**sweep_base, "carry_state": False})
    )

    orchestrator_carry = orchestrator_module.Orchestrator(cfg_carry)
    orchestrator_reset = orchestrator_module.Orchestrator(cfg_reset)

    result_carry = orchestrator_carry.run(
        rpm=1000.0,
        pipe_cells=2,
        pipe_length_m=0.2,
        pipe_diameter_m=0.05,
        bore_m=0.086,
        stroke_m=0.086,
        conrod_m=0.143,
        clearance_m3=1e-4,
        valve=valve,
    )
    result_reset = orchestrator_reset.run(
        rpm=1000.0,
        pipe_cells=2,
        pipe_length_m=0.2,
        pipe_diameter_m=0.05,
        bore_m=0.086,
        stroke_m=0.086,
        conrod_m=0.143,
        clearance_m3=1e-4,
        valve=valve,
    )

    err_carry = sum(entry["periodicity_error"] for entry in result_carry["sweep_results"])
    err_reset = sum(entry["periodicity_error"] for entry in result_reset["sweep_results"])
    assert err_carry < err_reset
