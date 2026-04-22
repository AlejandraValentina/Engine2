from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.engine_components import Engine
from pywavedyn import cli as py_cli


PRESET_PATH = Path("presets/honda_k20.json")
RPM_POINTS = [3000.0, 5000.0, 7000.0]
V2_SETTINGS = {
    "max_cycles": 3,
    "settle_cycles": 1,
    "min_periodicity": 0.5,
    "drop_invalid": False,
    "report_status": True,
    "pipe_cells": 6,
    "pipe_length_m": 0.35,
    "pipe_diameter_m": 0.04,
    "dt_max": 4e-4,
}


def _load_engine() -> Engine:
    raw = json.loads(PRESET_PATH.read_text(encoding="utf-8"))
    return Engine.from_dict(raw)


@pytest.mark.integration
def test_v1_v2_torque_power_plausibility_band_small_k20_case() -> None:
    """Cross-mode guardrail is only a coarse plausibility band, not a parity claim."""
    engine = _load_engine()

    v1_results = py_cli._dyno_results_v1(engine, RPM_POINTS)
    v2_results = py_cli._dyno_results_v2(engine, RPM_POINTS, v2_settings=V2_SETTINGS)

    assert len(v1_results) == len(RPM_POINTS)
    assert len(v2_results) == len(RPM_POINTS)

    for v1_entry, v2_entry in zip(v1_results, v2_results):
        assert v2_entry.get("status") == "ok", f"Unexpected v2 status at {v2_entry.get('rpm')}: {v2_entry}"
        for key in ("mean_torque_nm", "mean_power_hp"):
            v1_value = float(v1_entry[key])
            v2_value = float(v2_entry[key])
            assert math.isfinite(v1_value)
            assert math.isfinite(v2_value)
            assert v1_value > 0.0
            assert v2_value > 0.0

            ratio = v2_value / max(v1_value, 1e-9)
            assert 0.2 <= ratio <= 1.5, (
                f"Cross-mode {key} plausibility band failed at rpm={v1_entry['rpm']}: "
                f"v1={v1_value:.3f} v2={v2_value:.3f} ratio={ratio:.3f}"
            )

    assert float(v1_results[-1]["mean_power_hp"]) > float(v1_results[0]["mean_power_hp"])
    assert float(v2_results[-1]["mean_power_hp"]) > float(v2_results[0]["mean_power_hp"])
