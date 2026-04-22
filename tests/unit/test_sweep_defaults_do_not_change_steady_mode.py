import pytest

np = pytest.importorskip("numpy")

import numpy as np

import core.advanced.orchestrator as orchestrator_module
from core.advanced.coupling import ValveTiming


def test_sweep_defaults_do_not_change_steady_mode(monkeypatch: pytest.MonkeyPatch) -> None:
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
        return U.copy()

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

    monkeypatch.setattr(orchestrator_module, "boundary_flux_from_nozzle", fake_boundary_flux)
    monkeypatch.setattr(orchestrator_module, "muscl_hancock_step", fake_step)
    monkeypatch.setattr(orchestrator_module, "cfl_dt", fake_cfl_dt)

    base_cfg = dict(
        max_cycles=2,
        dt_max=1e-4,
        convergence_tol=0.0,
        periodicity_tol=0.0,
        periodicity_required=2,
    )

    cfg_baseline = orchestrator_module.OrchestratorConfig(**base_cfg)
    cfg_sweep_off = orchestrator_module.OrchestratorConfig(
        **base_cfg,
        sweep=orchestrator_module.SweepConfig(
            enabled=False,
            rpm_start=1000,
            rpm_end=2000,
            rpm_step=500,
            cycles_per_step=1,
        ),
    )

    valve = ValveTiming(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.0,
        seat_diameter_m=0.03,
        cd=1.0,
    )

    result_baseline = orchestrator_module.Orchestrator(cfg_baseline).run(
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
    result_sweep_off = orchestrator_module.Orchestrator(cfg_sweep_off).run(
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

    for key in ("angle_deg", "pressure", "ve", "trapped_mass", "indicated_work", "periodicity_metric"):
        assert np.allclose(result_baseline[key], result_sweep_off[key], atol=0.0)
    assert result_baseline["convergence_history"] == result_sweep_off["convergence_history"]
    assert "sweep_results" not in result_baseline
    assert "sweep_results" not in result_sweep_off
