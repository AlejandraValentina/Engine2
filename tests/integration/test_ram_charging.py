import pytest

np = pytest.importorskip("numpy")

from core.advanced.coupling import ValveTiming
from core.advanced.orchestrator import Orchestrator, OrchestratorConfig


@pytest.mark.integration
def test_ram_charging_sensitivity() -> None:
    cfg = OrchestratorConfig(dt_max=1e-4)
    solver = Orchestrator(cfg)
    valve = ValveTiming(open_start_deg=360.0, open_end_deg=540.0, max_lift_m=0.008, seat_diameter_m=0.03, cd=0.9)

    base = solver.run(
        rpm=3000.0,
        pipe_cells=20,
        pipe_length_m=0.4,
        pipe_diameter_m=0.04,
        bore_m=0.086,
        stroke_m=0.086,
        conrod_m=0.139,
        clearance_m3=5e-5,
        valve=valve,
    )
    tuned = solver.run(
        rpm=3000.0,
        pipe_cells=20,
        pipe_length_m=0.8,
        pipe_diameter_m=0.04,
        bore_m=0.086,
        stroke_m=0.086,
        conrod_m=0.139,
        clearance_m3=5e-5,
        valve=valve,
    )

    ve_base = max(base["ve"], default=0.0)
    ve_tuned = max(tuned["ve"], default=0.0)

    assert ve_base >= 0.9
    assert ve_tuned >= 0.9
    assert abs(ve_tuned - ve_base) >= 0.01
