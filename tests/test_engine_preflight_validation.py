from __future__ import annotations

from core.engine_components import Engine


def test_preflight_validate_with_issues_accepts_valid_preset() -> None:
    engine = Engine.load_from_file("presets/honda_k20.json")
    assert engine.preflight_validate_with_issues(operation="dyno", mode="v1") == []


def test_preflight_reports_absurd_rpm_configuration() -> None:
    engine = Engine()
    engine.block.redline_rpm = 500.0
    engine.camshaft.peak_rpm = 30000.0

    issues = engine.preflight_validate_with_issues(operation="dyno", mode="v1")

    assert any("Redline" in issue for issue in issues)
    assert any("Cam peak rpm" in issue for issue in issues)


def test_preflight_reports_conflicting_boost_configuration() -> None:
    engine = Engine()
    engine.turbo.enabled = True
    engine.turbo.target_boost_kpa = 60.0
    engine.turbo.compressor_map = [{"pr": 1.5, "flow": 0.1, "eff": 0.7}]
    engine.turbo.turbine_map = [{"pr": 1.6, "flow": 0.1, "eff": 0.7}]
    engine.supercharger.type = "Roots"
    engine.supercharger.boost_pressure_bar = 0.2

    issues = engine.preflight_validate_with_issues(operation="dyno", mode="v1")

    assert any("Turbo is enabled while supercharger.type is not 'NA'" in issue for issue in issues)
    assert any("supercharger.boost_pressure_bar" in issue for issue in issues)


def test_preflight_rejects_turbo_declared_through_supercharger_alias() -> None:
    engine = Engine.from_dict(
        {
            "block": {"bore": 73.0, "stroke": 82.0, "num_cylinders": 4, "redline_rpm": 6500.0},
            "head": {"compression_ratio": 9.9, "port_flow_cfm": 140.0, "port_flow_efficiency": 0.7},
            "camshaft": {"intake_lift": 8.5, "intake_duration": 220.0, "lobe_separation": 112.0, "peak_rpm": 4000.0},
            "intake": {"runner_length": 300.0, "runner_diameter": 34.0, "throttle_cfm": 350.0},
            "exhaust": {"header_primary_length": 400.0, "header_primary_diameter": 32.0},
            "combustion": {"thermal_efficiency": 0.4, "burn_duration": 35.0, "ignition_advance": 18.0, "afr": 12.0},
            "friction": {
                "friction_base_kpa": 34.0,
                "friction_linear_factor": 0.018,
                "friction_quadratic_factor": 1.6e-6,
                "global_scaling_factor": 1.0,
            },
            "fuel": {"energy_density": 44e6, "octane_rating": 95.0},
            "simulation_settings": {"air_temperature_c": 25.0, "air_pressure_bar": 1.013},
            "supercharger": {"type": "Turbo", "boost_pressure_bar": 0.8},
        }
    )

    issues = engine.preflight_validate_with_issues(operation="dyno", mode="v1")

    assert any("supercharger.type='Turbo'" in issue for issue in issues)


def test_preflight_requires_explicit_quick_dyno_v1_definition_for_sparse_json() -> None:
    engine = Engine.from_dict({})

    review = engine.preflight_review(operation="dyno", mode="v1")

    assert any("Quick Dyno v1 requires explicit engine JSON fields" in issue for issue in review["errors"])


def test_preflight_warns_when_legacy_ignition_field_is_promoted() -> None:
    engine = Engine.from_dict(
        {
            "block": {"bore": 73.0, "stroke": 82.0, "num_cylinders": 4, "redline_rpm": 6500.0},
            "head": {"compression_ratio": 9.9, "port_flow_cfm": 140.0, "port_flow_efficiency": 0.7},
            "camshaft": {"intake_lift": 8.5, "intake_duration": 220.0, "lobe_separation": 112.0, "peak_rpm": 4000.0},
            "intake": {"runner_length": 300.0, "runner_diameter": 34.0, "throttle_cfm": 350.0},
            "exhaust": {"header_primary_length": 400.0, "header_primary_diameter": 32.0},
            "combustion": {"thermal_efficiency": 0.4, "burn_duration": 35.0, "afr": 12.0},
            "friction": {
                "friction_base_kpa": 34.0,
                "friction_linear_factor": 0.018,
                "friction_quadratic_factor": 1.6e-6,
                "global_scaling_factor": 1.0,
            },
            "fuel": {"energy_density": 44e6, "octane_rating": 95.0},
            "simulation_settings": {
                "ignition_timing_btdc": 18.0,
                "air_temperature_c": 25.0,
                "air_pressure_bar": 1.013,
            },
        }
    )

    review = engine.preflight_review(operation="dyno", mode="v1")

    assert review["errors"] == []
    assert any("promoted to combustion.ignition_advance" in issue for issue in review["warnings"])


def test_preflight_allows_map_driven_turbo_without_target_when_wastegate_is_disabled() -> None:
    engine = Engine.from_dict(
        {
            "block": {"bore": 73.0, "stroke": 82.0, "num_cylinders": 4, "redline_rpm": 6500.0},
            "head": {"compression_ratio": 9.9, "port_flow_cfm": 140.0, "port_flow_efficiency": 0.7},
            "camshaft": {"intake_lift": 8.5, "intake_duration": 220.0, "lobe_separation": 112.0, "peak_rpm": 4000.0},
            "intake": {"runner_length": 300.0, "runner_diameter": 34.0, "throttle_cfm": 350.0},
            "exhaust": {"header_primary_length": 400.0, "header_primary_diameter": 32.0},
            "combustion": {"thermal_efficiency": 0.4, "burn_duration": 35.0, "ignition_advance": 18.0, "afr": 12.0},
            "friction": {
                "friction_base_kpa": 34.0,
                "friction_linear_factor": 0.018,
                "friction_quadratic_factor": 1.6e-6,
                "global_scaling_factor": 1.0,
            },
            "fuel": {"energy_density": 44e6, "octane_rating": 95.0},
            "simulation_settings": {"air_temperature_c": 25.0, "air_pressure_bar": 1.013},
            "turbo": {
                "enabled": True,
                "wastegate_enabled": False,
                "compressor_map": [{"flow_kg_s": 0.03, "pr": 1.8}],
                "turbine_map": [{"flow_kg_s": 0.03, "pr": 1.4}],
            },
        }
    )

    review = engine.preflight_review(operation="dyno", mode="v1")

    assert review["errors"] == []


def test_preflight_reports_missing_v2_requirements() -> None:
    engine = Engine()
    engine.head.exhaust_valve_seat_diameter_mm = 0.0
    engine.simulation_settings.gamma_air = 1.0
    engine.simulation_settings.gamma_exhaust = 1.0
    engine.simulation_settings.gas_constant_R = 0.0

    issues = engine.preflight_validate_with_issues(operation="full_scope", mode="v2")

    assert any("exhaust_valve_seat_diameter_mm" in issue for issue in issues)
    assert any("gamma_air and gamma_exhaust" in issue for issue in issues)
    assert any("gas_constant_R" in issue for issue in issues)


def test_preflight_review_separates_warnings_from_blockers() -> None:
    engine = Engine()
    engine.head.compression_ratio = 19.0
    engine.intake.runner_length = 1200.0

    review = engine.preflight_review(operation="dyno", mode="v1")

    assert review["errors"] == []
    assert any("Compression ratio" in issue for issue in review["warnings"])
    assert any("Intake runner length" in issue for issue in review["warnings"])
    assert engine.preflight_validate(operation="dyno", mode="v1", strict=True) is True


def test_legacy_preset_reports_missing_quick_dyno_definition_when_needed() -> None:
    engine = Engine.load_from_file("presets/legacy/custom_twin_230cc.json")

    review = engine.preflight_review(operation="dyno", mode="v1")

    assert any("head.port_flow_cfm" in issue for issue in review["errors"])
