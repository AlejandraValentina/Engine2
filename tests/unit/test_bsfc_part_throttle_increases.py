import pytest

import core.advanced.orchestrator as orchestrator_module
from core.advanced.coupling import ValveTiming
from core.engine_components import FuelConfig, Throttle


def _fake_run_cycles_quadratic(
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
    pos = self.cfg.throttle.position
    base_work = 1200.0
    base_air = 0.002
    indicated_work = base_work * pos * pos
    result = {
        "angle_deg": [0.0],
        "pressure": [101325.0],
        "ve": [pos],
        "trapped_mass": [pos],
        "indicated_work": [indicated_work],
        "periodicity_metric": [0.0],
        "convergence_history": [],
    }
    if track_pumping_work:
        result["pumping_work"] = [-150.0 * (1.0 - pos)]
    if track_map:
        result["map_estimate"] = [100000.0 * pos]
    if self.cfg.fuel.enabled:
        m_air_fresh = base_air * pos
        result["fuel_metrics"] = [
            orchestrator_module._compute_fuel_metrics(m_air_fresh, rpm, indicated_work, self.cfg.fuel)
        ]
    return state, result, 1


def _build_valve() -> ValveTiming:
    return ValveTiming(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.0,
        seat_diameter_m=0.03,
        cd=1.0,
    )


def test_bsfc_increases_at_part_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module.Orchestrator, "_run_cycles", _fake_run_cycles_quadratic)

    cfg = orchestrator_module.OrchestratorConfig(
        max_cycles=1,
        sweep=orchestrator_module.SweepConfig(
            enabled=True,
            rpm_start=2000,
            rpm_end=2500,
            rpm_step=500,
            cycles_per_step=1,
            throttle_position_grid=[1.0, 0.5],
        ),
        throttle=Throttle(enabled=True, position=1.0, body_diam_m=0.07),
        fuel=FuelConfig(enabled=True, mode="lambda", lambda_target=1.0),
    )
    orchestrator = orchestrator_module.Orchestrator(cfg)
    result = orchestrator.run(
        rpm=2000.0,
        pipe_cells=2,
        pipe_length_m=0.2,
        pipe_diameter_m=0.05,
        bore_m=0.086,
        stroke_m=0.086,
        conrod_m=0.143,
        clearance_m3=1e-4,
        valve=_build_valve(),
    )

    sweep_results = result["sweep_results"]
    bsfc_vals = [entry["bsfc_g_per_kwh"] for entry in sweep_results]
    assert bsfc_vals[0] < bsfc_vals[1]
