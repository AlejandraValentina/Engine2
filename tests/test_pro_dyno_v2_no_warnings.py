from __future__ import annotations

import warnings

import pytest

from core.engine_components import Engine
from core.pro_dyno_v2 import ProDynoV2Runner


def test_pro_dyno_v2_no_warnings() -> None:
    engine = Engine()
    runner = ProDynoV2Runner(
        engine,
        settings={
            "max_cycles": 2,
            "pipe_cells": 12,
            "pipe_length_m": 0.4,
            "pipe_diameter_m": 0.038,
            "dt_max": 1e-4,
        },
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("error", RuntimeWarning)
        runner.run_sweep([2000, 3000])

    assert len(caught) == 0
