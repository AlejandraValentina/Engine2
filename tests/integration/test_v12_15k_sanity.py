from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from core.engine_components import Engine
from pywavedyn import cli as py_cli


PRESET_PATH = Path("presets/f1_screamer_v12_1710cc_15k.json")
RPM_POINTS = [12000.0, 15000.0]


def _load_engine() -> tuple[Engine, dict]:
    raw = json.loads(PRESET_PATH.read_text(encoding="utf-8"))
    engine = Engine.from_dict(raw)
    return engine, raw


def _assert_finite_results(results: list[dict]) -> None:
    for entry in results:
        for key in ("mean_power_hp", "mean_torque_nm", "ve_actual", "bmep_bar"):
            value = float(entry.get(key, 0.0))
            assert math.isfinite(value), f"{key} not finite: {value}"


@pytest.mark.integration
def test_v12_15k_sanity() -> None:
    engine, raw = _load_engine()

    v1_results = py_cli._dyno_results_v1(engine, RPM_POINTS)
    assert v1_results, "v1 results empty"
    _assert_finite_results(v1_results)

    rpm_target = 15000.0
    v1_15k = next((entry for entry in v1_results if abs(entry["rpm"] - rpm_target) < 1e-6), None)
    assert v1_15k is not None, "missing 15k rpm point"
    assert v1_15k["ve_actual"] > 0.75
    assert v1_15k["mean_power_hp"] > 100.0

    v2_settings = {
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
    v2_results = py_cli._dyno_results_v2(engine, RPM_POINTS, v2_settings=v2_settings)
    assert v2_results, "v2 results empty"
    _assert_finite_results(v2_results)
    for entry in v2_results:
        if "status" in entry:
            assert entry["status"] != "failed"
    v2_15k = next((entry for entry in v2_results if abs(entry["rpm"] - rpm_target) < 1e-6), None)
    assert v2_15k is not None, "missing v2 15k rpm point"
    assert v2_15k["ve_actual"] > 0.75
    assert v2_15k["mean_power_hp"] > 250.0

    residual_cfg = getattr(engine.combustion, "residual_coupling", {}) or {}
    if bool(residual_cfg.get("enabled", False)):
        report = py_cli._build_knock_report(engine, raw, RPM_POINTS, coupling_mode="none")
        flags = [bool(item.get("knock_flag", False)) for item in report.get("results", [])]
        assert flags, "knock report empty"
        assert any(not flag for flag in flags), "knock is flagged at all rpm points"
