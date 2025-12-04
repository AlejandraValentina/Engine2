import pytest

np = pytest.importorskip("numpy")

from core.thermo import CylinderSimulator, piston_geometry
from core.engine_components import Engine


def test_piston_movement():
    angles = np.linspace(0.0, 720.0, 100)
    result = piston_geometry(angles, bore=86.0, stroke=86.0, conrod=139.0)
    volume = result[0]
    assert volume.shape == angles.shape
    assert np.all(np.isfinite(volume))
    # Volume should remain non-negative through the cycle
    assert float(np.min(volume)) >= 0.0


def test_engine_performance_k20(tmp_path):
    # Use the shipped K20 preset to ensure realistic setup
    engine = Engine.load_from_file("presets/honda_k20.json")
    sim = CylinderSimulator(engine)
    result = sim.run_cycle(6000.0)

    # Access volumetric efficiency regardless of key naming
    ve_value = None
    if "ve" in result:
        ve_value = result["ve"]
    elif "ve_percent" in result:
        ve_value = result["ve_percent"]
    elif "ve_actual" in result:
        ve_value = result["ve_actual"] * 100.0

    assert ve_value is not None
    assert np.isfinite(ve_value)
    assert result["mean_power_hp"] > 0.0
    assert result["mean_torque_nm"] > 0.0
