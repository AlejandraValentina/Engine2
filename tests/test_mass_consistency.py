import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def test_afr_change_shifts_output_monotonic() -> None:
    engine_rich = Engine()
    engine_lean = Engine()

    engine_rich.combustion.afr = 12.0
    engine_lean.combustion.afr = 16.0

    rich = CylinderSimulator(engine_rich).run_cycle(4000.0)
    lean = CylinderSimulator(engine_lean).run_cycle(4000.0)

    assert rich["mean_power_hp"] >= lean["mean_power_hp"]
    assert np.isfinite(rich["temperature"]).all()
    assert np.isfinite(lean["temperature"]).all()
