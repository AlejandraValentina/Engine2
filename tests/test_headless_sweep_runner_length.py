from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("numpy")

import numpy as np

from pywavedyn.cli import run_sweep


def test_headless_sweep_runner_length(tmp_path) -> None:
    out_path = tmp_path / "sweep.json"
    lengths = [220.0, 260.0, 300.0, 340.0, 380.0]

    engine_path = Path("presets/legacy/custom_twin_230cc.json").resolve()
    run_sweep(
        engine_path=engine_path,
        rpm=3000.0,
        out_path=out_path,
        runner_lengths=lengths,
    )

    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    results = payload.get("results", [])
    assert len(results) == len(lengths)

    powers = []
    torques = []
    for entry in results:
        assert entry["runner_length_mm"] in lengths
        assert entry["rpm"] == 3000.0
        power = float(entry["mean_power_hp"])
        torque = float(entry["mean_torque_nm"])
        bmep = float(entry["bmep_bar"])
        assert np.isfinite(power)
        assert np.isfinite(torque)
        assert np.isfinite(bmep)
        assert 0.0 <= power < 500.0
        assert 0.0 <= torque < 5000.0
        assert 0.0 <= bmep < 50.0
        powers.append(power)
        torques.append(torque)

    assert max(powers) > 0.0
    assert max(torques) > 0.0
