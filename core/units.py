"""Lightweight unit conversions used across the core models."""
from __future__ import annotations

BAR_TO_PA = 100000.0
IN_H2O_28_PA = 28.0 * 249.08891  # Pa at 4°C reference
CFM_TO_M3S = 0.00047194745


def bar_to_pa(x_bar: float) -> float:
    return x_bar * BAR_TO_PA


def mm_to_m(x_mm: float) -> float:
    return x_mm * 1e-3


def cc_to_m3(x_cc: float) -> float:
    return x_cc * 1e-6


def inch_h2o_to_pa(inches: float) -> float:
    return inches * 249.08891


def cfm_to_m3s(q_cfm: float) -> float:
    return q_cfm * CFM_TO_M3S

__all__ = [
    "bar_to_pa",
    "mm_to_m",
    "cc_to_m3",
    "inch_h2o_to_pa",
    "cfm_to_m3s",
    "BAR_TO_PA",
    "IN_H2O_28_PA",
    "CFM_TO_M3S",
]
