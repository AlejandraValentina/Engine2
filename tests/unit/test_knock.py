from __future__ import annotations

import math

import pytest

np = pytest.importorskip("numpy")

from core.knock import compute_knock_index


def test_knock_zero_rpm_returns_no_activation() -> None:
    angle = np.linspace(0.0, 720.0, 721)
    temperature = np.linspace(350.0, 900.0, 721)

    result = compute_knock_index(
        angle,
        temperature,
        rpm=0.0,
        start_angle_deg=360.0,
        residual_fraction=0.25,
        residual_temp_k=875.0,
    )

    assert result == {
        "knock_index": 0.0,
        "knock_flag": False,
        "endgas_temp_k": 0.0,
        "residual_temp_k": 875.0,
        "residual_fraction": 0.25,
    }


def test_knock_index_reports_expected_magnitude_without_activation() -> None:
    angle = np.linspace(0.0, 720.0, 721)
    temperature = np.full_like(angle, 500.0)
    config = {"A": 12.0, "B": 3200.0, "threshold": 0.5, "window_deg": 20.0, "residual_hot_k": 0.0}

    result = compute_knock_index(
        angle,
        temperature,
        rpm=3000.0,
        start_angle_deg=360.0,
        residual_fraction=0.4,
        residual_temp_k=1200.0,
        config=config,
    )

    expected_index = math.exp(12.0 - 3200.0 / 500.0) * 20.0 * (1.0 / (3000.0 * 6.0))

    assert result["knock_flag"] is False
    assert result["knock_index"] == pytest.approx(expected_index)
    assert result["endgas_base_temp_k"] == pytest.approx(500.0)
    assert result["endgas_temp_k"] == pytest.approx(500.0)
    assert result["residual_temp_k"] == pytest.approx(1200.0)
    assert result["window_deg"] == pytest.approx(20.0)
    assert result["threshold"] == pytest.approx(0.5)
    assert result["A"] == pytest.approx(12.0)
    assert result["B"] == pytest.approx(3200.0)


def test_knock_index_activates_when_hot_residuals_raise_endgas_temperature() -> None:
    angle = np.linspace(0.0, 720.0, 721)
    temperature = np.full_like(angle, 650.0)
    config = {"A": 17.0, "B": 3800.0, "threshold": 0.2, "window_deg": 40.0, "residual_hot_k": 1.0}

    result = compute_knock_index(
        angle,
        temperature,
        rpm=3000.0,
        start_angle_deg=360.0,
        residual_fraction=0.5,
        residual_temp_k=1300.0,
        config=config,
    )

    expected_endgas = 650.0 + 0.5 * (1300.0 - 650.0)
    expected_index = math.exp(17.0 - 3800.0 / expected_endgas) * 40.0 * (1.0 / (3000.0 * 6.0))

    assert result["knock_flag"] is True
    assert result["endgas_base_temp_k"] == pytest.approx(650.0)
    assert result["endgas_temp_k"] == pytest.approx(expected_endgas)
    assert result["knock_index"] == pytest.approx(expected_index)
    assert result["knock_index"] >= result["threshold"]
