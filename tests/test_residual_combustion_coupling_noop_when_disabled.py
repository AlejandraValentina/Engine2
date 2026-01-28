import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def test_residual_combustion_coupling_noop_when_disabled() -> None:
    engine = Engine()
    baseline = CylinderSimulator(engine).run_cycle(3000.0)["mean_power_hp"]

    engine_disabled = Engine()
    engine_disabled.combustion.residual_coupling = {"enabled": False, "k": 10.0, "min_factor": 0.1}
    disabled = CylinderSimulator(engine_disabled).run_cycle(3000.0)["mean_power_hp"]

    assert disabled == pytest.approx(baseline, rel=1e-12, abs=1e-12)
