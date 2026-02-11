from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np
from scipy.io import wavfile

from pywavedyn import cli as py_cli


@pytest.mark.system
def test_audio_exhaust_plenum_smoother(tmp_path: Path) -> None:
    engine = Path("presets/legacy/custom_twin_230cc.json").resolve()
    runner_path = tmp_path / "runner.wav"
    plenum_path = tmp_path / "plenum.wav"

    py_cli.run_audio(
        engine_path=engine,
        rpm=2500.0,
        duration=0.01,
        sample_rate=3000,
        out_path=runner_path,
        firing_order=None,
        source="primary",
    )
    py_cli.run_audio(
        engine_path=engine,
        rpm=2500.0,
        duration=0.01,
        sample_rate=3000,
        out_path=plenum_path,
        firing_order=None,
        source="exhaust_plenum",
    )

    _sr_r, runner = wavfile.read(runner_path)
    _sr_p, plenum = wavfile.read(plenum_path)

    runner = runner.astype(np.float64)
    plenum = plenum.astype(np.float64)
    if runner.size < 2 or plenum.size < 2:
        pytest.fail("Audio outputs too short")

    hf_runner = float(np.mean(np.abs(np.diff(runner))))
    hf_plenum = float(np.mean(np.abs(np.diff(plenum))))
    assert hf_plenum <= hf_runner
