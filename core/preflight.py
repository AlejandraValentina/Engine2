from __future__ import annotations

from typing import Any


_QUICK_DYNO_V1_REQUIRED_FIELDS = (
    "block.bore",
    "block.stroke",
    "block.num_cylinders",
    "block.redline_rpm",
    "head.compression_ratio",
    "head.port_flow_cfm",
    "head.port_flow_efficiency",
    "camshaft.intake_lift",
    "camshaft.intake_duration",
    "camshaft.lobe_separation",
    "camshaft.peak_rpm",
    "intake.runner_length",
    "intake.runner_diameter",
    "intake.throttle_cfm",
    "exhaust.header_primary_length",
    "exhaust.header_primary_diameter",
    "combustion.thermal_efficiency",
    "combustion.burn_duration",
    "combustion.ignition_advance",
    "combustion.afr",
    "friction.friction_base_kpa",
    "friction.friction_linear_factor",
    "friction.friction_quadratic_factor",
    "friction.global_scaling_factor",
    "fuel.energy_density",
    "fuel.octane_rating",
    "simulation_settings.air_temperature_c",
    "simulation_settings.air_pressure_bar",
)


def collect_preflight_report(engine: Any, *, operation: str = "dyno", mode: str = "v1") -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    def fail(message: str) -> None:
        if message not in errors:
            errors.append(message)

    def warn(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    provided_fields = getattr(engine, "provided_fields", None)
    if mode == "v1" and operation in {"dyno", "sweep", "map"} and provided_fields is not None:
        missing_explicit = [path for path in _QUICK_DYNO_V1_REQUIRED_FIELDS if path not in provided_fields]
        if missing_explicit:
            fail(
                "Quick Dyno v1 requires explicit engine JSON fields and will not silently rely on defaults for: "
                + ", ".join(missing_explicit)
            )

    displacement_cc = float(engine.block.displacement_cc)
    if displacement_cc < 50.0 or displacement_cc > 20000.0:
        fail(
            f"Displacement {displacement_cc:.1f} cc is outside the supported run range (50 .. 20000 cc). "
            "Adjust bore, stroke, or cylinder count before running."
        )

    firing_order = list(getattr(engine.block, "firing_order", []))
    n_cyl = int(engine.block.num_cylinders)
    if firing_order and len(firing_order) != n_cyl:
        fail(
            f"Firing order length {len(firing_order)} does not match cylinder count {n_cyl}. "
            "Update block.firing_order so it has one entry per cylinder."
        )
    if firing_order and sorted(firing_order) != list(range(1, n_cyl + 1)):
        fail(
            "Firing order must contain each cylinder exactly once using 1..N numbering. "
            "Correct block.firing_order before running."
        )

    compression_ratio = float(engine.head.compression_ratio)
    if compression_ratio < 5.0 or compression_ratio > 18.0:
        warn(
            f"Compression ratio {compression_ratio:.2f}:1 is outside the recommended range (5.0 .. 18.0). "
            "Review head.compression_ratio for the intended fuel and duty cycle."
        )

    redline = float(engine.block.redline_rpm)
    if redline < 1000.0 or redline > 22000.0:
        fail(
            f"Redline {redline:.0f} rpm is outside the supported run range (1000 .. 22000 rpm). "
            "Review block.redline_rpm."
        )

    peak_rpm = float(engine.camshaft.peak_rpm)
    if peak_rpm < 500.0 or peak_rpm > max(redline * 1.25, 1000.0):
        warn(
            f"Cam peak rpm {peak_rpm:.0f} is far from redline {redline:.0f}. "
            "Review camshaft.peak_rpm if the engine should make power in the requested band."
        )

    intake_runner_length = float(engine.intake.runner_length)
    if not (50.0 <= intake_runner_length <= 1000.0):
        warn(
            f"Intake runner length {intake_runner_length:.1f} mm is outside the recommended range (50 .. 1000 mm). "
            "Review intake.runner_length."
        )

    intake_runner_diameter = float(engine.intake.runner_diameter)
    if not (10.0 <= intake_runner_diameter <= 120.0):
        warn(
            f"Intake runner diameter {intake_runner_diameter:.1f} mm is outside the recommended range (10 .. 120 mm). "
            "Review intake.runner_diameter."
        )

    header_length = float(engine.exhaust.header_primary_length)
    if not (50.0 <= header_length <= 2000.0):
        warn(
            f"Header primary length {header_length:.1f} mm is outside the recommended range (50 .. 2000 mm). "
            "Review exhaust.header_primary_length."
        )

    header_diameter = float(engine.exhaust.header_primary_diameter)
    if not (10.0 <= header_diameter <= 120.0):
        warn(
            f"Header primary diameter {header_diameter:.1f} mm is outside the recommended range (10 .. 120 mm). "
            "Review exhaust.header_primary_diameter."
        )

    turbo = getattr(engine, "turbo", None)
    supercharger = getattr(engine, "supercharger", None)
    supercharger_type = str(getattr(supercharger, "type", "NA") or "NA")
    supercharger_boost_bar = float(getattr(supercharger, "boost_pressure_bar", 0.0) or 0.0)
    if supercharger_type.lower() == "turbo":
        fail(
            "supercharger.type='Turbo' is ambiguous and no longer accepted for Quick Dyno. "
            "Use turbo.enabled with turbo.target_boost_kpa/target_pr, or use a non-turbo supercharger type."
        )
    if supercharger_boost_bar > 0.0 and supercharger_type == "NA":
        fail(
            "supercharger.boost_pressure_bar is positive while supercharger.type is 'NA'. "
            "Set a real supercharger type or move the boost request into the turbo block."
        )
    if turbo is not None and bool(turbo.enabled):
        if supercharger is not None and getattr(supercharger, "type", "NA") != "NA":
            fail(
                "Turbo is enabled while supercharger.type is not 'NA'. Disable one boost system or set "
                "supercharger.type to 'NA'."
            )
        if supercharger_boost_bar > 0.0:
            fail(
                "Turbo is enabled while supercharger.boost_pressure_bar is also positive. "
                "Quick Dyno uses the turbo block only; clear supercharger.boost_pressure_bar."
            )
        turbo_has_target = turbo.target_boost_kpa is not None or turbo.target_pr is not None
        if not turbo_has_target and bool(getattr(turbo, "wastegate_enabled", True)):
            fail(
                "Turbo is enabled with wastegate control but no target boost was provided. "
                "Set turbo.target_boost_kpa or turbo.target_pr, or disable wastegate control for map-driven boost."
            )
        if turbo.target_boost_kpa is not None and float(turbo.target_boost_kpa) <= 0.0:
            fail("turbo.target_boost_kpa must be positive when turbo is enabled.")
        if turbo.target_pr is not None and float(turbo.target_pr) <= 1.0:
            fail("turbo.target_pr must be greater than 1.0 when turbo is enabled.")
        if not list(turbo.compressor_map):
            fail("Turbo is enabled but turbo.compressor_map is empty. Provide at least one compressor map point.")
        if not list(turbo.turbine_map):
            fail("Turbo is enabled but turbo.turbine_map is empty. Provide at least one turbine map point.")
        if not (0.0 <= float(turbo.intercooler_efficiency) <= 1.0):
            fail("turbo.intercooler_efficiency must be within [0, 1].")
    elif turbo is not None:
        turbo_block_populated = (
            turbo.target_boost_kpa is not None
            or turbo.target_pr is not None
            or bool(list(getattr(turbo, "compressor_map", [])))
            or bool(list(getattr(turbo, "turbine_map", [])))
        )
        if turbo_block_populated:
            warn("turbo.* is populated but turbo.enabled is false, so Quick Dyno v1 will ignore the turbo block.")

    sim = engine.simulation_settings
    if bool(getattr(sim, "enable_heat_transfer_1d", False)) and float(getattr(sim, "wall_temperature_k", 0.0)) <= 0.0:
        fail(
            "1D heat transfer is enabled but simulation_settings.wall_temperature_k is not positive. "
            "Set a positive wall temperature or disable 1D heat transfer."
        )

    if operation in {"dyno", "scope", "sweep", "map", "full_scope", "v2"}:
        if float(engine.head.port_flow_efficiency) <= 0.0:
            fail("head.port_flow_efficiency must be positive to run simulations.")
        if float(engine.combustion.thermal_efficiency) <= 0.0:
            fail("combustion.thermal_efficiency must be positive to run simulations.")

    if operation in {"scope", "full_scope"} and float(engine.exhaust.collector_length) <= 0.0:
        fail("exhaust.collector_length must be positive to run scope or full-scope.")

    if mode == "v2" or operation == "v2":
        if float(engine.head.exhaust_valve_seat_diameter_mm or 0.0) <= 0.0:
            fail("V2 requires a positive head.exhaust_valve_seat_diameter_mm.")
        if float(sim.gamma_air) <= 1.0 or float(sim.gamma_exhaust) <= 1.0:
            fail("V2 requires gamma_air and gamma_exhaust greater than 1.0.")
        if float(sim.gas_constant_R) <= 0.0:
            fail("V2 requires simulation_settings.gas_constant_R to be positive.")

    for note in getattr(engine, "schema_warnings", []) or []:
        warn(str(note))

    return {"errors": errors, "warnings": warnings}


def collect_preflight_issues(engine: Any, *, operation: str = "dyno", mode: str = "v1") -> list[str]:
    report = collect_preflight_report(engine, operation=operation, mode=mode)
    return [*report["errors"], *report["warnings"]]
