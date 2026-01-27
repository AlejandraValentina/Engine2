from __future__ import annotations

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

import numpy as np
from scipy.io import wavfile

from acoustics.audio_generator import save_multicylinder_wav
from core.engine_components import Engine


def test_audio_multicyl_wav_nonempty(tmp_path) -> None:
    engine = Engine.load_from_file("presets/legacy/custom_twin_230cc.json")
    engine.simulation_settings.enable_0d_to_1d_exhaust_coupling = True

    out_path = tmp_path / "multicyl.wav"
    rpm = 2500.0
    duration = 0.4
    sample_rate = 8000

    waveform = save_multicylinder_wav(
        engine,
        rpm=rpm,
        firing_order=engine.block.firing_order,
        duration=duration,
        sample_rate=sample_rate,
        filename=out_path,
    )

    assert out_path.exists()
    assert out_path.stat().st_size > 0
    assert waveform.size > 0

    sr, data = wavfile.read(out_path)
    assert sr == sample_rate
    assert data.size > 0

    expected_samples = int(duration * sample_rate)
    assert abs(int(data.shape[0]) - expected_samples) <= 1

    rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
    assert rms > 1e-4
