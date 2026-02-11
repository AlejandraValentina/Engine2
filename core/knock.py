from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class KnockConfig:
    A: float = 17.0
    B: float = 3800.0
    threshold: float = 1.0
    window_deg: float = 40.0
    residual_hot_k: float = 1.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "KnockConfig":
        if not isinstance(data, dict):
            return cls()
        return cls(
            A=float(data.get("A", data.get("knock_A", 17.0))),
            B=float(data.get("B", data.get("knock_B", 3800.0))),
            threshold=float(data.get("threshold", data.get("knock_threshold", 1.0))),
            window_deg=float(data.get("window_deg", data.get("knock_window_deg", 40.0))),
            residual_hot_k=float(data.get("residual_hot_k", data.get("knock_residual_hot_k", 1.0))),
        )


def _interp_angle(angle_deg: np.ndarray, values: np.ndarray, target_deg: float) -> float:
    if angle_deg.size == 0 or values.size == 0:
        raise ValueError("Angle/temperature arrays must be non-empty")
    target = float(target_deg % 720.0)
    return float(np.interp(target, angle_deg, values))


def estimate_endgas_temperature(
    angle_deg: np.ndarray,
    temperature_k: np.ndarray,
    start_angle_deg: float,
    residual_fraction: float,
    residual_temp_k: float | None = None,
    residual_hot_k: float = 1.0,
) -> tuple[float, float, float]:
    angle_deg = np.asarray(angle_deg, dtype=float)
    temperature_k = np.asarray(temperature_k, dtype=float)
    if angle_deg.size != temperature_k.size:
        raise ValueError("Angle/temperature arrays must have matching length")

    base_angle = float(start_angle_deg - 1.0)
    T_base = _interp_angle(angle_deg, temperature_k, base_angle)

    if residual_temp_k is None or not math.isfinite(residual_temp_k):
        mask_exhaust = angle_deg >= 540.0
        if np.any(mask_exhaust):
            residual_temp_k = float(np.mean(temperature_k[mask_exhaust]))
        else:
            residual_temp_k = float(np.max(temperature_k))

    residual_fraction = float(np.clip(residual_fraction, 0.0, 1.0))
    residual_hot_k = max(float(residual_hot_k), 0.0)
    hot_frac = float(np.clip(residual_fraction * residual_hot_k, 0.0, 1.0))
    T_residual = max(float(residual_temp_k), T_base)
    T_endgas = T_base + hot_frac * (T_residual - T_base)
    return float(T_endgas), float(residual_temp_k), float(T_base)


def compute_knock_index(
    angle_deg: np.ndarray,
    temperature_k: np.ndarray,
    rpm: float,
    start_angle_deg: float,
    residual_fraction: float,
    residual_temp_k: float | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, float | bool]:
    if rpm <= 0.0:
        return {
            "knock_index": 0.0,
            "knock_flag": False,
            "endgas_temp_k": 0.0,
            "residual_temp_k": float(residual_temp_k or 0.0),
            "residual_fraction": float(residual_fraction),
        }

    cfg = KnockConfig.from_dict(config)
    T_endgas, residual_temp_k_used, T_base = estimate_endgas_temperature(
        angle_deg,
        temperature_k,
        start_angle_deg,
        residual_fraction,
        residual_temp_k=residual_temp_k,
        residual_hot_k=cfg.residual_hot_k,
    )

    window_deg = max(float(cfg.window_deg), 1e-6)
    dt_per_deg = 1.0 / (float(rpm) * 6.0)
    integrand = math.exp(cfg.A - cfg.B / max(T_endgas, 1e-6))
    knock_index = float(integrand * window_deg * dt_per_deg)
    knock_flag = bool(knock_index >= cfg.threshold)
    return {
        "knock_index": knock_index,
        "knock_flag": knock_flag,
        "endgas_temp_k": float(T_endgas),
        "endgas_base_temp_k": float(T_base),
        "residual_temp_k": float(residual_temp_k_used),
        "residual_fraction": float(residual_fraction),
        "window_deg": window_deg,
        "threshold": float(cfg.threshold),
        "A": float(cfg.A),
        "B": float(cfg.B),
    }
