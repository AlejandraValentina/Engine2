import copy

import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator


@pytest.mark.integration
def test_residuals_reduce_power_at_high_overlap_trend() -> None:
    engine = Engine()
    engine.camshaft.intake_duration = 320.0
    engine.camshaft.exhaust_duration = 320.0
    engine.camshaft.lobe_separation = 90.0

    baseline = CylinderSimulator(engine).run_cycle(4000.0)["mean_power_hp"]

    coupled_engine = copy.deepcopy(engine)
    coupled_engine.combustion.residual_coupling = {"enabled": True, "k": 1.2, "min_factor": 0.3}
    coupled = CylinderSimulator(coupled_engine).run_cycle(4000.0)["mean_power_hp"]

    assert coupled < baseline
