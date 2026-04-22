from __future__ import annotations

from core.engine_wizard import WizardSpec, build_engine_from_wizard, review_wizard_spec, summarize_engine_for_wizard


def test_basic_inline4_wizard_builds_valid_engine() -> None:
    spec = WizardSpec(
        complexity="Basic",
        architecture="Inline-4",
        aspiration="Naturally Aspirated",
        rpm_start=2000,
        rpm_end=8500,
        objective="peak_power",
    )

    engine = build_engine_from_wizard(spec)

    assert engine.preflight_validate_with_issues(operation="dyno", mode="v1") == []
    assert engine.block.num_cylinders == 4
    assert engine.turbo.enabled is False


def test_expert_turbo_v8_wizard_build_is_deterministic_and_traceable() -> None:
    spec = WizardSpec(
        complexity="Expert",
        architecture="V8",
        aspiration="Turbo",
        rpm_start=1800,
        rpm_end=6500,
        objective="spool",
        displacement_cc=5700.0,
        compression_ratio=9.8,
        runner_length_mm=290.0,
        header_length_mm=520.0,
        runner_diameter_mm=46.0,
        header_diameter_mm=35.0,
        peak_rpm=4200.0,
        redline_rpm=7000.0,
        thermal_efficiency=0.5,
        port_flow_efficiency=0.68,
        intake_duration_deg=246.0,
        exhaust_duration_deg=250.0,
        intake_lift_mm=10.1,
        exhaust_lift_mm=9.8,
        lobe_separation_deg=114.0,
        ignition_advance_deg=24.0,
        target_boost_kpa=65.0,
    )

    engine_a = build_engine_from_wizard(spec)
    engine_b = build_engine_from_wizard(spec)
    summary = summarize_engine_for_wizard(engine_a, spec)

    assert engine_a.to_dict() == engine_b.to_dict()
    assert engine_a.preflight_validate_with_issues(operation="dyno", mode="v1") == []
    assert engine_a.turbo.enabled is True
    assert summary["Architecture"] == "V8"
    assert summary["Aspiration"] == "Turbo"
    assert "Boost" in summary


def test_basic_level_ignores_advanced_and_expert_overrides() -> None:
    spec = WizardSpec(
        complexity="Basic",
        architecture="Inline-4",
        aspiration="Naturally Aspirated",
        objective="peak_power",
        displacement_cc=3200.0,
        compression_ratio=8.5,
        runner_length_mm=600.0,
        header_length_mm=1200.0,
        runner_diameter_mm=60.0,
        thermal_efficiency=0.3,
    )

    engine = build_engine_from_wizard(spec)
    review = review_wizard_spec(spec)

    assert abs(engine.block.displacement_cc - 2000.0) < 1.0
    assert engine.head.compression_ratio != 8.5
    assert engine.intake.runner_length != 600.0
    assert engine.intake.runner_diameter != 60.0
    assert review["warnings"]


def test_advanced_level_applies_mid_level_inputs_but_not_expert_ones() -> None:
    spec = WizardSpec(
        complexity="Advanced",
        architecture="Inline-4",
        aspiration="Naturally Aspirated",
        objective="torque_mean",
        displacement_cc=2400.0,
        compression_ratio=11.2,
        runner_length_mm=390.0,
        header_length_mm=710.0,
        runner_diameter_mm=55.0,
        target_boost_kpa=90.0,
    )

    engine = build_engine_from_wizard(spec)
    review = review_wizard_spec(spec)

    assert abs(engine.block.displacement_cc - 2400.0) < 2.0
    assert engine.head.compression_ratio == 11.2
    assert engine.intake.runner_length == 390.0
    assert engine.exhaust.header_primary_length == 710.0
    assert engine.intake.runner_diameter != 55.0
    assert any("Advanced level ignores expert-only overrides" in issue for issue in review["warnings"])


def test_wizard_spec_reports_invalid_rpm_window() -> None:
    review = review_wizard_spec(
        WizardSpec(
            complexity="Basic",
            architecture="Inline-4",
            aspiration="Naturally Aspirated",
            rpm_start=7000,
            rpm_end=6500,
        )
    )

    assert any("Target RPM end must be greater than target RPM start." in issue for issue in review["errors"])
