from __future__ import annotations

import math

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


def mass_flow_nozzle(
    p_up: float,
    T_up: float,
    p_down: float,
    area: float,
    gamma: float,
    gas_constant: float,
    cd: float = 1.0,
) -> tuple[float, float, float]:
    """Estimate compressible nozzle mass flow with optional choking.

    Returns (m_dot, T_exit, h0). The upstream pressure/temperature are treated
    as stagnation (total) conditions.
    """

    if area <= 0.0 or p_up <= 0.0 or T_up <= 0.0:
        return 0.0, max(T_up, 1.0), 0.0

    gamma = float(gamma)
    gas_constant = float(gas_constant)
    cd = max(min(float(cd), 1.2), 0.0)

    pr = max(min(p_down / max(p_up, 1e-12), 1.0), 0.0)
    critical = (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
    choked = pr <= critical

    if choked:
        pr_eff = critical
    else:
        pr_eff = pr

    temp_ratio = pr_eff ** ((gamma - 1.0) / gamma)
    T_exit = max(T_up * temp_ratio, 1.0)

    if choked:
        flow_coeff = math.sqrt(gamma / gas_constant) * (2.0 / (gamma + 1.0)) ** (
            (gamma + 1.0) / (2.0 * (gamma - 1.0))
        )
        m_dot = cd * area * p_up / math.sqrt(T_up) * flow_coeff
    else:
        term = (pr ** (2.0 / gamma) - pr ** ((gamma + 1.0) / gamma))
        term = max(term, 0.0)
        flow_coeff = math.sqrt(2.0 * gamma / (gas_constant * (gamma - 1.0)) * term)
        m_dot = cd * area * p_up / math.sqrt(T_up) * flow_coeff

    cp = gamma * gas_constant / max(gamma - 1.0, 1e-9)
    h0 = cp * T_up
    return float(m_dot), float(T_exit), float(h0)


def build_exhaust_coupling(
    angle: np.ndarray,
    p_stag: np.ndarray,
    t_stag: np.ndarray,
    firing_order: list[int],
) -> dict[int, dict[str, np.ndarray]]:
    """Create per-cylinder coupling data from a shared 0D trace."""

    coupling: dict[int, dict[str, np.ndarray]] = {}
    for cyl in firing_order:
        coupling[int(cyl)] = {
            "angle": np.asarray(angle, dtype=float),
            "p_stag": np.asarray(p_stag, dtype=float),
            "t_stag": np.asarray(t_stag, dtype=float),
        }
    return coupling
