from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import numpy as np

from acoustics.audio_generator import render_pressure_trace


def test_render_pressure_trace_rms_and_limit() -> None:
    times = np.linspace(0.0, 0.1, 50)
    pressures = 101325.0 + 500.0 * np.sin(2.0 * np.pi * 80.0 * times)
    wave = render_pressure_trace(times, pressures, sample_rate=8000)
    assert wave is not None
    assert wave.size > 0
    rms = float(np.sqrt(np.mean(wave.astype(np.float64) ** 2)))
    assert rms > 0.1
    assert np.max(np.abs(wave)) <= 1.0
