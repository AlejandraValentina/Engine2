from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.engine_components import Engine
from core.full_network import run_full_scope


@pytest.mark.integration
def test_full_network_runner_length_shifts_torque_peak() -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json")
    base = Engine.from_dict(json.loads(preset.read_text(encoding="utf-8")))

    short_engine = Engine.from_dict(base.to_dict())
    long_engine = Engine.from_dict(base.to_dict())

    short_engine.intake.runner_length = 180.0
    long_engine.intake.runner_length = 520.0

    rpm_low = 2000.0
    rpm_high = 4500.0

    low_short = run_full_scope(short_engine, duration_s=0.01, max_steps=120, target_dx=0.05, rpm=rpm_low)
    high_short = run_full_scope(short_engine, duration_s=0.01, max_steps=120, target_dx=0.05, rpm=rpm_high)
    low_long = run_full_scope(long_engine, duration_s=0.01, max_steps=120, target_dx=0.05, rpm=rpm_low)
    high_long = run_full_scope(long_engine, duration_s=0.01, max_steps=120, target_dx=0.05, rpm=rpm_high)

    torque_low_short = low_short.per_cyl[0]["mean_torque_nm"]
    torque_high_short = high_short.per_cyl[0]["mean_torque_nm"]
    torque_low_long = low_long.per_cyl[0]["mean_torque_nm"]
    torque_high_long = high_long.per_cyl[0]["mean_torque_nm"]

    assert torque_high_short >= torque_low_short
    assert torque_low_long >= torque_high_long
