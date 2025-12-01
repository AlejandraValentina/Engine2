from typing import Optional

import numpy as np
from scipy import interpolate, signal
from scipy.io import wavfile


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
