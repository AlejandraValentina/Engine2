import pytest

import core.advanced.orchestrator as orchestrator_module
from core.engine_components import FuelConfig


def test_fuel_lambda_mode_basic() -> None:
    cfg = FuelConfig(
        enabled=True,
        mode="lambda",
        lambda_target=1.0,
        afr_stoich=14.7,
    )
    metrics = orchestrator_module._compute_fuel_metrics(
        m_air_fresh_per_cycle_kg=0.0005,
        rpm=3000.0,
        indicated_work=100.0,
        cfg=cfg,
    )
    assert abs(metrics["m_fuel_per_cycle_kg"] - (0.0005 / 14.7)) < 1e-12


def test_fuel_alternative_stoich_and_lhv_change_metrics_reasonably() -> None:
    gasoline = FuelConfig(
        enabled=True,
        mode="lambda",
        lambda_target=1.0,
        afr_stoich=14.7,
        lhv_j_per_kg=43e6,
    )
    alt_fuel = FuelConfig(
        enabled=True,
        mode="lambda",
        lambda_target=1.0,
        afr_stoich=9.0,
        lhv_j_per_kg=26.8e6,
    )

    gasoline_metrics = orchestrator_module._compute_fuel_metrics(
        m_air_fresh_per_cycle_kg=0.0005,
        rpm=3000.0,
        indicated_work=100.0,
        cfg=gasoline,
    )
    alt_metrics = orchestrator_module._compute_fuel_metrics(
        m_air_fresh_per_cycle_kg=0.0005,
        rpm=3000.0,
        indicated_work=100.0,
        cfg=alt_fuel,
    )

    assert alt_metrics["afr_used"] == pytest.approx(9.0)
    assert alt_metrics["m_fuel_per_cycle_kg"] > gasoline_metrics["m_fuel_per_cycle_kg"]
    assert alt_metrics["fuel_flow_kg_s"] > gasoline_metrics["fuel_flow_kg_s"]
    assert alt_metrics["bsfc_g_per_kwh"] > gasoline_metrics["bsfc_g_per_kwh"]
    assert alt_metrics["eta_bte"] < gasoline_metrics["eta_bte"]
