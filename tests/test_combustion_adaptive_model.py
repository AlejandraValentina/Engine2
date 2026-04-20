from __future__ import annotations

import pytest

from core.engine_components import Engine
from core.thermo import CylinderSimulator


def _run(engine: Engine, rpm: float) -> dict:
    return CylinderSimulator(engine).run_cycle(rpm)


def test_adaptive_combustion_disabled_is_noop() -> None:
    engine_base = Engine()
    engine_disabled = Engine()
    engine_disabled.combustion.adaptive_model = {
        "enabled": False,
        "duration_rpm_per_krpm": 5.0,
        "ca50_load_per_bar": -1.0,
    }

    base = _run(engine_base, 4000.0)
    disabled = _run(engine_disabled, 4000.0)

    assert float(disabled["mean_power_hp"]) == pytest.approx(float(base["mean_power_hp"]))
    assert float(disabled["mean_torque_nm"]) == pytest.approx(float(base["mean_torque_nm"]))
    assert float(disabled["trace"]["burn_duration_used"]) == pytest.approx(float(base["trace"]["burn_duration_used"]))
    assert disabled["trace"]["adaptive_combustion"]["enabled"] is False


def test_adaptive_combustion_rpm_increases_burn_duration() -> None:
    engine = Engine()
    engine.combustion.adaptive_model = {
        "enabled": True,
        "duration_rpm_per_krpm": 2.0,
        "duration_min_deg": 10.0,
        "duration_max_deg": 120.0,
    }

    low = _run(engine, 2000.0)
    high = _run(engine, 7000.0)

    assert float(high["trace"]["burn_duration_used"]) > float(low["trace"]["burn_duration_used"])
    assert high["trace"]["adaptive_combustion"]["status"] == "applied"


def test_adaptive_combustion_boosted_load_shortens_and_advances() -> None:
    na_engine = Engine()
    na_engine.combustion.adaptive_model = {
        "enabled": True,
        "duration_load_per_bar": -0.8,
        "duration_boost_per_kpa": -0.04,
        "ca50_load_per_bar": -0.2,
        "ca50_boost_per_kpa": -0.02,
        "duration_min_deg": 10.0,
        "duration_max_deg": 120.0,
    }

    boosted_engine = Engine.from_dict(na_engine.to_dict())
    boosted_engine.supercharger.boost_pressure_bar = 0.8

    na = _run(na_engine, 5000.0)
    boosted = _run(boosted_engine, 5000.0)

    assert float(boosted["trace"]["burn_duration_used"]) < float(na["trace"]["burn_duration_used"])
    assert float(boosted["trace"]["ca50_target_used"]) < float(na["trace"]["ca50_target_used"])
    assert float(boosted["trace"]["adaptive_combustion"]["signals"]["boost_kpa"]) > 0.0


def test_adaptive_combustion_leaner_mixture_retards_and_lengthens() -> None:
    rich_engine = Engine()
    rich_engine.combustion.afr = 12.5
    rich_engine.combustion.adaptive_model = {
        "enabled": True,
        "duration_lambda_per_lambda": 10.0,
        "ca50_lambda_per_lambda": 4.0,
        "duration_min_deg": 10.0,
        "duration_max_deg": 120.0,
    }

    lean_engine = Engine.from_dict(rich_engine.to_dict())
    lean_engine.combustion.afr = 16.0

    rich = _run(rich_engine, 4000.0)
    lean = _run(lean_engine, 4000.0)

    assert float(lean["trace"]["lambda_rel_used"]) > float(rich["trace"]["lambda_rel_used"])
    assert float(lean["trace"]["burn_duration_used"]) > float(rich["trace"]["burn_duration_used"])
    assert float(lean["trace"]["ca50_target_used"]) > float(rich["trace"]["ca50_target_used"])


def test_adaptive_combustion_residual_proxy_retards_and_lengthens() -> None:
    base_engine = Engine()
    base_engine.camshaft.intake_duration = 220.0
    base_engine.camshaft.exhaust_duration = 220.0
    base_engine.camshaft.lobe_separation = 114.0
    base_engine.combustion.adaptive_model = {
        "enabled": True,
        "duration_residual_per_frac": 40.0,
        "ca50_residual_per_frac": 15.0,
        "duration_min_deg": 10.0,
        "duration_max_deg": 120.0,
    }

    overlap_engine = Engine.from_dict(base_engine.to_dict())
    overlap_engine.camshaft.intake_duration = 280.0
    overlap_engine.camshaft.exhaust_duration = 280.0
    overlap_engine.camshaft.lobe_separation = 104.0

    base = _run(base_engine, 4500.0)
    overlap = _run(overlap_engine, 4500.0)

    base_res = float(base["trace"]["adaptive_combustion"]["signals"]["residual_fraction_proxy"])
    overlap_res = float(overlap["trace"]["adaptive_combustion"]["signals"]["residual_fraction_proxy"])
    assert overlap_res > base_res
    assert float(overlap["trace"]["burn_duration_used"]) > float(base["trace"]["burn_duration_used"])
    assert float(overlap["trace"]["ca50_target_used"]) > float(base["trace"]["ca50_target_used"])
