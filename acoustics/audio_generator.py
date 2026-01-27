from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from scipy import interpolate, signal
from scipy.io import wavfile

from core.engine_components import Engine


class AudioSynthesizer:
    """Collects pressure samples and renders them to audio.

    Samples are interpolated to a fixed-rate waveform (default 44.1 kHz),
    optionally high-pass filtered to remove DC bias, normalized to [-1, 1],
    and saved as a WAV file.
    """

    def __init__(self, sample_rate: int = 44_100):
        self.sample_rate = sample_rate
        self.times: list[float] = []
        self.pressures: list[float] = []

    def add_sample(self, sim_time: float, pressure: float) -> None:
        """Append a raw (time, pressure) sample from the solver."""
        self.times.append(float(sim_time))
        self.pressures.append(float(pressure))

    def render_waveform(self) -> Optional[np.ndarray]:
        """Return a normalized, resampled waveform array or ``None`` if empty."""
        if len(self.times) < 2:
            print("[AudioSynthesizer] Not enough samples to generate audio.")
            return None

        times = np.asarray(self.times, dtype=np.float64)
        pressures = np.asarray(self.pressures, dtype=np.float64)

        sort_idx = np.argsort(times)
        times = times[sort_idx]
        pressures = pressures[sort_idx]

        duration = times[-1] - times[0]
        if duration <= 0:
            print("[AudioSynthesizer] Invalid duration; cannot synthesize audio.")
            return None

        target_samples = int(np.ceil(duration * self.sample_rate)) + 1
        target_times = np.linspace(times[0], times[-1], target_samples)

        interpolator = interpolate.interp1d(
            times, pressures, kind="linear", fill_value="extrapolate"
        )
        resampled = interpolator(target_times)

        cutoff_hz = 20.0
        b, a = signal.butter(2, cutoff_hz / (0.5 * self.sample_rate), btype="highpass")
        resampled = signal.filtfilt(b, a, resampled)

        p_min = resampled.min()
        p_max = resampled.max()
        if np.isclose(p_max, p_min):
            normalized = np.zeros_like(resampled, dtype=np.float32)
        else:
            normalized = 2.0 * (resampled - p_min) / (p_max - p_min) - 1.0
            normalized = normalized.astype(np.float32)

        return normalized

    def save_waveform(self, waveform: np.ndarray, filename: str) -> None:
        if waveform is None or len(waveform) == 0:
            print("[AudioSynthesizer] Nothing to save.")
            return
        wavfile.write(filename, self.sample_rate, waveform.astype(np.float32))
        print(f"[AudioSynthesizer] Saved {filename} ({len(waveform)} samples)")

    def process_and_save(self, filename: str) -> None:
        """Resample collected data to audio rate and write a WAV file."""
        normalized = self.render_waveform()
        if normalized is None:
            return
        self.save_waveform(normalized, filename)


def _single_cylinder_pulse(
    engine: Engine,
    rpm: float,
    sample_rate: int,
) -> np.ndarray:
    rpm = max(float(rpm), 1.0)
    sample_rate = max(int(sample_rate), 1000)
    period = 120.0 / rpm
    samples = max(int(round(period * sample_rate)), 16)
    t = np.arange(samples, dtype=np.float64) / sample_rate

    length_m = max(float(engine.exhaust.header_primary_length) * 1e-3, 0.2)
    c_sound = 500.0
    f0 = c_sound / (4.0 * length_m)
    f0 = float(np.clip(f0, 80.0, 400.0))

    decay = np.exp(-t * f0 * 1.5)
    wave = np.sin(2.0 * np.pi * f0 * t)
    wave += 0.4 * np.sin(2.0 * np.pi * 2.0 * f0 * t)
    wave *= decay

    peak = float(np.max(np.abs(wave)))
    if peak > 0.0:
        wave = wave / peak
    return wave.astype(np.float32)


def synthesize_multicylinder_waveform(
    engine: Engine,
    rpm: float,
    firing_order: list[int] | None,
    duration: float,
    sample_rate: int,
) -> np.ndarray:
    """Render a multi-cylinder waveform using the firing order mix."""

    rpm = max(float(rpm), 1.0)
    duration = max(float(duration), 0.01)
    sample_rate = int(sample_rate)
    firing_order = list(firing_order or engine.block.firing_order or [1])

    single_wave = _single_cylinder_pulse(engine, rpm, sample_rate)
    return generate_full_engine_sound(
        single_wave,
        rpm,
        firing_order,
        sample_rate,
        duration=duration,
    )


def save_multicylinder_wav(
    engine: Engine,
    rpm: float,
    firing_order: list[int] | None,
    duration: float,
    sample_rate: int,
    filename: str | Path,
) -> np.ndarray:
    """Generate and save a deterministic multi-cylinder WAV file."""

    waveform = synthesize_multicylinder_waveform(
        engine,
        rpm=rpm,
        firing_order=firing_order,
        duration=duration,
        sample_rate=sample_rate,
    )
    if waveform.size == 0:
        raise ValueError("Empty waveform generated; check inputs")
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(path, int(sample_rate), waveform.astype(np.float32))
    return waveform


def generate_full_engine_sound(
    single_cylinder_wave: np.ndarray,
    rpm: float,
    firing_order: list[int],
    sample_rate: int,
    duration: float = 2.0,
) -> np.ndarray:
    """Mix a single-cylinder waveform across the firing order to emulate a full engine."""

    if single_cylinder_wave is None or len(single_cylinder_wave) == 0:
        return np.array([], dtype=np.float32)

    wave = np.asarray(single_cylinder_wave, dtype=np.float32)
    cyl_count = max(len(firing_order), 1)
    rpm = max(float(rpm), 1.0)
    delta_t = 120.0 / (rpm * cyl_count)
    delta_samples = int(round(delta_t * sample_rate))
    if delta_samples <= 0:
        delta_samples = 1
    period_samples = delta_samples * cyl_count

    total_samples = int(duration * sample_rate)
    mixed = np.zeros(total_samples, dtype=np.float32)

    for idx, _cyl in enumerate(firing_order or [0]):
        start = idx * delta_samples
        pos = start
        while pos < total_samples:
            chunk = min(wave.size, total_samples - pos)
            mixed[pos : pos + chunk] += wave[:chunk]
            pos += period_samples

    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed = mixed / peak
    return mixed.astype(np.float32)
