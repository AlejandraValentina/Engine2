from __future__ import annotations

from core.engine_components import Engine


def test_induction_classification_prefers_turbo_enabled() -> None:
    engine = Engine()
    engine.supercharger.type = "Roots"
    engine.supercharger.boost_pressure_bar = 0.8
    engine.turbo.enabled = True

    assert engine.induction_classification() == "Turbo"
    assert engine.induction_mode_name() == "Turbo"


def test_set_induction_mode_keeps_boost_systems_exclusive() -> None:
    engine = Engine()
    engine.turbo.enabled = True
    engine.turbo.target_boost_kpa = 90.0
    engine.supercharger.type = "Roots"
    engine.supercharger.boost_pressure_bar = 0.7

    engine.set_induction_mode("Roots")
    assert engine.turbo.enabled is False
    assert engine.supercharger.type == "Roots"
    assert engine.induction_classification() == "Supercharger"

    engine.set_induction_mode("NA")
    assert engine.turbo.enabled is False
    assert engine.supercharger.type == "NA"
    assert engine.supercharger.boost_pressure_bar == 0.0
    assert engine.induction_classification() == "NA"

    engine.supercharger.boost_pressure_bar = 0.9
    engine.set_induction_mode("Turbo")
    assert engine.turbo.enabled is True
    assert engine.supercharger.type == "NA"
    assert engine.supercharger.boost_pressure_bar == 0.0
    assert engine.induction_classification() == "Turbo"
