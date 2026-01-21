import pytest

import core.advanced.orchestrator as orchestrator_module
from core.advanced.coupling import ValveTiming
from core.engine_components import Throttle


def _fake_run_cycles_linear(
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
    indicated_work = 1000.0 * pos
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
        result["pumping_work"] = [-200.0 * (1.0 - pos)]
    if track_map:
        result["map_estimate"] = [100000.0 * pos]
    return state, result, 1


def _build_valve() -> ValveTiming:
    return ValveTiming(
        open_start_deg=0.0,
        open_end_deg=10.0,
        max_lift_m=0.0,
        seat_diameter_m=0.03,
        cd=1.0,
    )


def test_throttle_part_load_monotonic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module.Orchestrator, "_run_cycles", _fake_run_cycles_linear)

    cfg = orchestrator_module.OrchestratorConfig(
        max_cycles=1,
        sweep=orchestrator_module.SweepConfig(
            enabled=True,
            rpm_start=1000,
            rpm_end=2000,
            rpm_step=500,
            cycles_per_step=1,
            throttle_position_grid=[1.0, 0.6, 0.3],
        ),
        throttle=Throttle(enabled=True, position=1.0, body_diam_m=0.07),
    )
    orchestrator = orchestrator_module.Orchestrator(cfg)
    result = orchestrator.run(
        rpm=1000.0,
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
    map_vals = [entry["map_estimate"] for entry in sweep_results]
    brake_vals = [entry["brake_power_w"] for entry in sweep_results]

    assert map_vals[0] > map_vals[1] > map_vals[2]
    assert brake_vals[0] > brake_vals[1] > brake_vals[2]


def test_defaults_unchanged_without_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module.Orchestrator, "_run_cycles", _fake_run_cycles_linear)

    cfg = orchestrator_module.OrchestratorConfig(
        max_cycles=1,
        sweep=orchestrator_module.SweepConfig(
            enabled=True,
            rpm_start=1000,
            rpm_end=1500,
            rpm_step=500,
            cycles_per_step=1,
        ),
        throttle=Throttle(enabled=False),
    )
    orchestrator = orchestrator_module.Orchestrator(cfg)
    result = orchestrator.run(
        rpm=1000.0,
        pipe_cells=2,
        pipe_length_m=0.2,
        pipe_diameter_m=0.05,
        bore_m=0.086,
        stroke_m=0.086,
        conrod_m=0.143,
        clearance_m3=1e-4,
        valve=_build_valve(),
    )

    for entry in result["sweep_results"]:
        assert "map_estimate" not in entry
        assert "pumping_work" not in entry
        assert "brake_power_w" not in entry
