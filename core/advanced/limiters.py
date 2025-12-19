from __future__ import annotations

import numpy as np


def minmod(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    same_sign = (a * b) > 0.0
    out = np.zeros_like(a)
    out[same_sign] = np.where(np.abs(a[same_sign]) < np.abs(b[same_sign]), a[same_sign], b[same_sign])
    return out
