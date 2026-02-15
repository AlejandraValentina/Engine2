import math

import pytest

from core.engine_components import Block
from core.units import bar_to_pa, cc_to_m3


def test_displacement_updates_with_stroke_change():
    block = Block(bore=86.0, stroke=86.0, num_cylinders=4)
    base_disp = block.displacement_cc
    block.stroke = 100.0
    new_disp = block.displacement_cc
    assert new_disp > base_disp
    assert math.isclose(new_disp / base_disp, 100.0 / 86.0, rel_tol=1e-3)


def test_unit_helpers():
    assert bar_to_pa(1.0) == pytest.approx(100000.0)
    assert cc_to_m3(1000.0) == pytest.approx(1e-3)
