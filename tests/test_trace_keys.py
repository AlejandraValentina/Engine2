import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def test_trace_keys_present() -> None:
    engine = Engine()
    result = CylinderSimulator(engine).run_cycle(3000.0)
    trace = result.get("trace")
    assert isinstance(trace, dict)
    for key in (
        "ve_prelim",
        "ve_cam_factor",
        "ve_mach_factor",
        "ve_flow_cap_factor",
        "ve_final",
        "eta_combustion_used",
        "start_angle_used",
        "burn_duration_used",
        "ca50_target_used",
    ):
        assert key in trace
        if key != "ca50_target_used":
            assert trace[key] == trace[key]
