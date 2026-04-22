import pytest

np = pytest.importorskip("numpy")

import numpy as np

from core.advanced.combustion import (
    CombustionConfig,
    combustion_qdot,
    wiebe_dxb_dtheta,
    wiebe_xb,
)


def test_combustion_wiebe_integrates_to_one() -> None:
    start = 0.0
    duration = 60.0
    a = 5.0
    m = 2.0
    theta = np.linspace(start, start + duration, 2001)
    dxb = np.array([wiebe_dxb_dtheta(t, start, duration, a, m) for t in theta])
    integral = np.trapezoid(dxb, theta)
    xb_end = wiebe_xb(start + duration, start, duration, a, m)
    assert xb_end == pytest.approx(1.0, rel=1e-3, abs=1e-3)
    assert integral == pytest.approx(1.0, rel=1e-3, abs=1e-3)


def test_combustion_residuals_increase_duration_reduce_peak() -> None:
    cfg = CombustionConfig(
        enabled=True,
        duration_deg=60.0,
        duration_residual_k=1.0,
        wiebe_a=5.0,
        wiebe_m=2.0,
    )
    start = 0.0
    duration_base = cfg.duration_deg
    duration_res = cfg.duration_deg * (1.0 + cfg.duration_residual_k * 0.5)
    assert duration_res > duration_base

    theta_base = np.linspace(start, start + duration_base, 1001)
    theta_res = np.linspace(start, start + duration_res, 1001)
    dxb_base = np.array([wiebe_dxb_dtheta(t, start, duration_base, cfg.wiebe_a, cfg.wiebe_m) for t in theta_base])
    dxb_res = np.array([wiebe_dxb_dtheta(t, start, duration_res, cfg.wiebe_a, cfg.wiebe_m) for t in theta_res])
    assert np.max(dxb_res) < np.max(dxb_base)


def test_orchestrator_combustion_disabled_is_zero_Qdot() -> None:
    cfg = CombustionConfig(enabled=False)
    qdot = combustion_qdot(360.0, 2000.0, 0.5, 1.0, cfg)
    assert qdot == 0.0


def test_orchestrator_combustion_enabled_produces_finite_Qdot() -> None:
    cfg = CombustionConfig(enabled=True)
    qdot = combustion_qdot(360.0, 2000.0, 0.5, 1.0, cfg)
    assert np.isfinite(qdot)
    assert qdot >= 0.0
