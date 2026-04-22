import pytest

pytest.importorskip("numpy")

from core.engine_components import Engine
from core.full_network import run_full_scope


@pytest.mark.stress
def test_network_adversarial_no_hang() -> None:
    engine = Engine()
    engine.intake.runner_diameter = 5.0
    engine.exhaust.header_primary_diameter = 5.0
    engine.throttle.enabled = True
    engine.throttle.position = 0.1

    try:
        result = run_full_scope(engine, duration_s=0.01, max_steps=120, target_dx=0.05)
        assert result.status in {"complete", "max_steps"}
    except RuntimeError as exc:
        assert "max_steps" in str(exc) or "time_budget" in str(exc)
