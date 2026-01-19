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
