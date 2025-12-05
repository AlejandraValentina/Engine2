from __future__ import annotations

import numpy as np


def compute_pressure_matrix(history: list[np.ndarray], gamma: float) -> np.ndarray:
    """Convert a list of conservative-state histories into a pressure matrix.

    Parameters
    ----------
    history:
        List of arrays with shape (cells, 3) storing ``[rho, rho*u, rho*E]``.
    gamma:
        Specific heat ratio used to recover pressure from the energy equation.

    Returns
    -------
    np.ndarray
        Matrix of shape ``(frames, cells)`` with pressures in Pascals. If the
        input history is empty, returns an empty ``(0, 0)`` array.
    """

    if not history:
        return np.empty((0, 0))

    gamma = float(gamma) if np.isfinite(gamma) else 1.4
    pressures: list[np.ndarray] = []
    for state in history:
        if state.shape[1] < 3:
            raise ValueError("State must have three conserved variables")
        rho = state[:, 0]
        momentum = state[:, 1]
        energy = state[:, 2]
        kinetic = 0.5 * (momentum ** 2) / np.maximum(rho, 1e-12)
        p_grid = (gamma - 1.0) * (energy - kinetic)
        pressures.append(p_grid)

    return np.vstack(pressures)


def compute_image_levels(matrix: np.ndarray) -> tuple[float, float]:
    """Derive visualization levels for a heatmap from data percentiles.

    Uses 5th/95th percentiles of finite values to avoid saturation while
    adapting to different engine operating points. Falls back to a small range
    around the median if the spread collapses.
    """

    if matrix.size == 0:
        return (0.0, 1.0)

    finite_vals = matrix[np.isfinite(matrix)]
    if finite_vals.size == 0:
        return (0.0, 1.0)

    lower, upper = np.percentile(finite_vals, [5.0, 95.0])
    if not np.isfinite(lower) or not np.isfinite(upper):
        return (0.0, 1.0)

    if upper - lower < 1e-9:
        center = 0.5 * (lower + upper)
        span = max(abs(center) * 0.05, 1.0)
        return (center - span, center + span)

    padding = 0.05 * (upper - lower)
    return (lower - padding, upper + padding)
