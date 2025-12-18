import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def _peak_pressure_angle(result):
    angles = result["angle"]
    pressures = result["pressure"]
    mask = (angles >= 360.0) & (angles <= 540.0)
    idx = np.argmax(pressures[mask])
    return angles[mask][idx]


def test_ca50_phasing_shifts_peak_pressure():
    engine_base = Engine()
    engine_base.combustion.target_ca50_deg_atdc = 10.0
    res_base = CylinderSimulator(engine_base).run_cycle(4000.0)

    engine_late = Engine()
    engine_late.combustion.target_ca50_deg_atdc = 25.0
    res_late = CylinderSimulator(engine_late).run_cycle(4000.0)

    assert _peak_pressure_angle(res_late) > _peak_pressure_angle(res_base)


def test_wall_temperature_reduces_heat_loss():
    engine_cool = Engine()
    engine_cool.simulation_settings.wall_temperature_k = 350.0
    res_cool = CylinderSimulator(engine_cool).run_cycle(4000.0)

    engine_warm = Engine()
    engine_warm.simulation_settings.wall_temperature_k = 550.0
    res_warm = CylinderSimulator(engine_warm).run_cycle(4000.0)

    assert res_warm["mean_power_hp"] > res_cool["mean_power_hp"]
