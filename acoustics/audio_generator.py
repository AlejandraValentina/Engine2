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

    def process_and_save(self, filename: str) -> None:
        """Resample collected data to audio rate and write a WAV file."""
        if len(self.times) < 2:
            print("[AudioSynthesizer] Not enough samples to generate audio.")
            return

        times = np.asarray(self.times, dtype=np.float64)
        pressures = np.asarray(self.pressures, dtype=np.float64)

        # Ensure chronological order.
        sort_idx = np.argsort(times)
        times = times[sort_idx]
        pressures = pressures[sort_idx]

        duration = times[-1] - times[0]
        if duration <= 0:
            print("[AudioSynthesizer] Invalid duration; cannot synthesize audio.")
            return

        target_samples = int(np.ceil(duration * self.sample_rate)) + 1
        target_times = np.linspace(times[0], times[-1], target_samples)

        interpolator = interpolate.interp1d(
            times, pressures, kind="linear", fill_value="extrapolate"
        )
        resampled = interpolator(target_times)

        # High-pass filter to remove DC offset (20 Hz cutoff by default).
        cutoff_hz = 20.0
        b, a = signal.butter(2, cutoff_hz / (0.5 * self.sample_rate), btype="highpass")
        resampled = signal.filtfilt(b, a, resampled)

        # Normalize to [-1, 1].
        p_min = resampled.min()
        p_max = resampled.max()
        if np.isclose(p_max, p_min):
            normalized = np.zeros_like(resampled, dtype=np.float32)
        else:
            normalized = 2.0 * (resampled - p_min) / (p_max - p_min) - 1.0
            normalized = normalized.astype(np.float32)

        wavfile.write(filename, self.sample_rate, normalized)
        print(f"[AudioSynthesizer] Saved {filename} ({len(normalized)} samples)")
