import json
import math
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

def test_calculate_mass_flow_rate_zero_drop():
    numerics = pytest.importorskip("core.numerics")
    mdot = numerics.calculate_mass_flow_rate(101325.0, 101325.0, 300.0, 0.01, 1.0)
    assert mdot == pytest.approx(0.0, abs=1e-9)


def test_calculate_mass_flow_rate_choked_flow():
    numerics = pytest.importorskip("core.numerics")
    p_up = 200000.0
    p_down_low = p_up * 0.1
    p_down_lower = p_up * 0.01
    mdot_low = numerics.calculate_mass_flow_rate(p_up, p_down_low, 300.0, 0.01, 1.0)
    mdot_lower = numerics.calculate_mass_flow_rate(p_up, p_down_lower, 300.0, 0.01, 1.0)
    assert mdot_low > 0.0
    assert mdot_lower == pytest.approx(mdot_low, rel=1e-6)


def test_calculate_mass_flow_rate_reverse_flow():
    numerics = pytest.importorskip("core.numerics")
    mdot = numerics.calculate_mass_flow_rate(100000.0, 150000.0, 300.0, 0.01, 1.0)
    assert mdot < 0.0


def test_flux_vector_shape():
    numerics = pytest.importorskip("core.numerics")
    import numpy as np

    U = np.array([1.2, 0.3, 1.0e5], dtype=float)
    F = numerics.flux_vector(U)
    assert F.shape == (3,)
    assert np.all(np.isfinite(F))


def test_engine_save_load(tmp_path: Path):
    from core.engine_components import Engine

    engine = Engine()
    engine.block.bore = 95.5
    target = tmp_path / "temp_test.json"
    engine.save_to_file(str(target))

    loaded = Engine.load_from_file(str(target))
    assert loaded.block.bore == pytest.approx(95.5)


def test_displacement_calculation():
    from core.engine_components import Engine

    engine = Engine()
    engine.block.bore = 100.0
    engine.block.stroke = 100.0
    engine.block.num_cylinders = 4
    expected_cc = math.pi * (0.1 ** 2) * 0.1 / 4.0 * 4 * 1e6
    assert engine.block.displacement_cc == pytest.approx(expected_cc, rel=1e-4)
