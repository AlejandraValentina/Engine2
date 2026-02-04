from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np
from scipy.io import wavfile


@pytest.mark.integration
def test_audio_exhaust_plenum_smoother(tmp_path: Path) -> None:
    engine = Path("presets/legacy/custom_twin_230cc.json").resolve()
    runner_path = tmp_path / "runner.wav"
    plenum_path = tmp_path / "plenum.wav"

    cmd_base = [
        sys.executable,
        "-m",
        "pywavedyn.cli",
        "audio",
        "--engine",
        str(engine),
        "--rpm",
        "2500",
        "--duration",
        "0.02",
        "--sample-rate",
        "6000",
    ]

    subprocess.run(cmd_base + ["--source", "primary", "--out", str(runner_path)], check=True, capture_output=True, text=True)
    subprocess.run(
        cmd_base + ["--source", "exhaust_plenum", "--out", str(plenum_path)],
        check=True,
        capture_output=True,
        text=True,
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
