from __future__ import annotations

import math

import pytest

import core.advanced.orchestrator as orchestrator_module
from core.advanced.combustion import CombustionConfig
from core.advanced.coupling import ValveTiming
from core.advanced.plenum_cv import IntakePlenumConfig
from core.advanced.solver_1d import ShockCFLConfig, ShockCFLSubstepsConfig
from core.engine_components import FuelConfig, Throttle, WallThermalConfig


def _build_valve() -> ValveTiming:
    return ValveTiming(
        open_start_deg=360.0,
        open_end_deg=540.0,
        max_lift_m=0.008,
        seat_diameter_m=0.03,
        cd=0.9,
    )


def test_opt_in_combo_combustion_and_wall_thermal_runs_finite() -> None:
    cfg = orchestrator_module.OrchestratorConfig(
        max_cycles=1,
        dt_max=8e-5,
        convergence_tol=0.0,
        periodicity_tol=0.0,
        periodicity_required=1,
        combustion=CombustionConfig(enabled=True),
        fuel=FuelConfig(enabled=True, mode="lambda", lambda_target=1.0),
        wall_thermal=WallThermalConfig(
            enabled=True,
            h_model="constant",
            h_w_per_m2k=150.0,
            area_m2=0.05,
            m_wall_kg=1.0,
            cp_wall_j_per_kgk=500.0,
            twall_init_k=400.0,
        ),
    )

    result = orchestrator_module.Orchestrator(cfg).run(
        rpm=2500.0,
        pipe_cells=5,
        pipe_length_m=0.25,
        pipe_diameter_m=0.04,
        bore_m=0.086,
        stroke_m=0.086,
        conrod_m=0.143,
        clearance_m3=5e-5,
        valve=_build_valve(),
    )

    assert result["fuel_metrics"], "fuel/combustion combo should keep fuel metrics available"
    assert math.isfinite(float(result["ve"][-1]))
    assert math.isfinite(float(result["indicated_work"][-1]))
    assert result["convergence_history"]


def test_opt_in_combo_shock_cfl_with_numba_runs_finite() -> None:
    pytest.importorskip("numba")

    cfg = orchestrator_module.OrchestratorConfig(
        max_cycles=1,
        dt_max=8e-5,
        convergence_tol=0.0,
        periodicity_tol=0.0,
        periodicity_required=1,
        use_numba_1d=True,
        shock_cfl=ShockCFLConfig(
            enabled=True,
            k=6.0,
            min_factor=0.25,
            substeps=ShockCFLSubstepsConfig(enabled=True, max_substeps=4),
        ),
    )

    result = orchestrator_module.Orchestrator(cfg).run(
        rpm=2500.0,
        pipe_cells=5,
        pipe_length_m=0.25,
        pipe_diameter_m=0.04,
        bore_m=0.086,
        stroke_m=0.086,
        conrod_m=0.143,
        clearance_m3=5e-5,
        valve=_build_valve(),
    )

    assert math.isfinite(float(result["ve"][-1]))
    assert math.isfinite(float(result["indicated_work"][-1]))
    assert result["convergence_history"]
    last = result["convergence_history"][-1]
    assert math.isfinite(float(last["err_periodicity_1d"]))


def test_opt_in_combo_throttle_plenum_prefill_wires_initial_state(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, float] = {}

    def fake_run_cycles(
        self: orchestrator_module.Orchestrator,
        rpm: float,
        pipe_cells: int,
        pipe_length_m: float,
        pipe_diameter_m: float,
        bore_m: float,
        stroke_m: float,
        conrod_m: float,
        clearance_m3: float,
        valve: ValveTiming,
        junction_totals,
        *,
        max_cycles: int,
        convergence_enabled: bool,
        state,
        cycle_offset: int,
        sweep_step: int | None,
        sweep_rpm: float | None,
        check_finite: bool,
        track_pumping_work: bool = False,
        track_map: bool = False,
    ):
        if state is None:
            state = orchestrator_module._build_initial_state(self.cfg, pipe_cells, clearance_m3)
        assert state.plenum is not None
        captured["p0"] = float(state.p0)
        captured["T0"] = float(state.T0)
        captured["Y_init"] = float(state.Y_init)
        captured["throttle_pos"] = float(state.throttle_pos)
        result = {
            "angle_deg": [0.0],
            "pressure": [101325.0],
            "ve": [0.6],
            "ve_cycle": [0.6],
            "trapped_mass": [1e-4],
            "indicated_work": [50.0],
            "periodicity_metric": [0.0],
            "convergence_history": [],
        }
        return state, result, 1

    monkeypatch.setattr(orchestrator_module.Orchestrator, "_run_cycles", fake_run_cycles)

    cfg = orchestrator_module.OrchestratorConfig(
        max_cycles=1,
        dt_max=1e-5,
        convergence_tol=0.0,
        periodicity_tol=0.0,
        periodicity_required=1,
        throttle=Throttle(enabled=True, position=0.4, body_diam_m=0.024, cd=0.95),
        intake_plenum=IntakePlenumConfig(enabled=True, volume_m3=0.0015, p_init_pa=101325.0, t_init_k=300.0, y_init=1.0),
        pipe_prefill=orchestrator_module.PipePrefillConfig(
            enabled=True,
            auto=True,
            auto_amb_p_Pa=101325.0,
            auto_amb_T_K=300.0,
            exhaust_prefill_T_K=700.0,
        ),
    )

    result = orchestrator_module.Orchestrator(cfg).run(
        rpm=2000.0,
        pipe_cells=3,
        pipe_length_m=0.2,
        pipe_diameter_m=0.04,
        bore_m=0.086,
        stroke_m=0.086,
        conrod_m=0.143,
        clearance_m3=5e-5,
        valve=_build_valve(),
    )

    assert math.isfinite(float(result["ve"][-1]))
    assert captured["p0"] == pytest.approx(101325.0)
    assert captured["T0"] == pytest.approx(300.0)
    assert captured["Y_init"] == pytest.approx(1.0)
    assert captured["throttle_pos"] == pytest.approx(0.4)
