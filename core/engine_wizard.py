from __future__ import annotations

from dataclasses import dataclass
import math

from core.engine_components import (
    Block,
    Camshaft,
    Combustion,
    CylinderHead,
    Engine,
    ExhaustSystem,
    Friction,
    IntakeSystem,
    SimulationSettings,
    Supercharger,
    Throttle,
    Turbo,
)


ARCHITECTURE_PRESETS: dict[str, dict[str, object]] = {
    "Inline-4": {
        "num_cylinders": 4,
        "config": "L",
        "bank_angle": 0.0,
        "firing_order": [1, 3, 4, 2],
        "displacement_cc": 2000.0,
    },
    "V6": {
        "num_cylinders": 6,
        "config": "V",
        "bank_angle": 60.0,
        "firing_order": [1, 4, 2, 5, 3, 6],
        "displacement_cc": 3500.0,
    },
    "V8": {
        "num_cylinders": 8,
        "config": "V",
        "bank_angle": 90.0,
        "firing_order": [1, 8, 4, 3, 6, 5, 7, 2],
        "displacement_cc": 5700.0,
    },
    "Single Cylinder": {
        "num_cylinders": 1,
        "config": "L",
        "bank_angle": 0.0,
        "firing_order": [1],
        "displacement_cc": 450.0,
    },
}

OBJECTIVE_LABELS = {
    "torque_mean": "Torque bias",
    "peak_power": "Peak power bias",
    "spool": "Spool bias",
    "efficiency": "Efficiency bias",
    "sound": "Sound bias",
}

COMPLEXITY_FIELDS = {
    "Basic": ["use_case", "architecture", "aspiration", "rpm_start", "rpm_end", "objective"],
    "Advanced": [
        "use_case",
        "architecture",
        "aspiration",
        "rpm_start",
        "rpm_end",
        "objective",
        "displacement_cc",
        "compression_ratio",
        "runner_length_mm",
        "header_length_mm",
    ],
    "Expert": [
        "use_case",
        "architecture",
        "aspiration",
        "rpm_start",
        "rpm_end",
        "objective",
        "displacement_cc",
        "compression_ratio",
        "runner_length_mm",
        "header_length_mm",
        "runner_diameter_mm",
        "header_diameter_mm",
        "peak_rpm",
        "redline_rpm",
        "thermal_efficiency",
        "port_flow_efficiency",
        "intake_duration_deg",
        "exhaust_duration_deg",
        "intake_lift_mm",
        "exhaust_lift_mm",
        "lobe_separation_deg",
        "ignition_advance_deg",
        "target_boost_kpa",
    ],
}


@dataclass
class WizardSpec:
    complexity: str = "Basic"
    use_case: str = "Street"
    architecture: str = "Inline-4"
    aspiration: str = "Naturally Aspirated"
    rpm_start: int = 2000
    rpm_end: int = 8000
    objective: str = "peak_power"
    displacement_cc: float | None = None
    compression_ratio: float | None = None
    runner_length_mm: float | None = None
    runner_diameter_mm: float | None = None
    header_length_mm: float | None = None
    header_diameter_mm: float | None = None
    peak_rpm: float | None = None
    redline_rpm: float | None = None
    thermal_efficiency: float | None = None
    port_flow_efficiency: float | None = None
    intake_duration_deg: float | None = None
    exhaust_duration_deg: float | None = None
    intake_lift_mm: float | None = None
    exhaust_lift_mm: float | None = None
    lobe_separation_deg: float | None = None
    ignition_advance_deg: float | None = None
    target_boost_kpa: float | None = None


def _displacement_per_cylinder(displacement_cc: float, cylinders: int) -> float:
    return max(float(displacement_cc), 1.0) / max(int(cylinders), 1)


def _bore_stroke_from_displacement(displacement_cc: float, cylinders: int, objective: str) -> tuple[float, float]:
    per_cyl_cc = _displacement_per_cylinder(displacement_cc, cylinders)
    if objective == "torque_mean":
        stroke = 92.0
    elif objective == "peak_power":
        stroke = 82.0
    elif objective == "spool":
        stroke = 86.0
    elif objective == "efficiency":
        stroke = 84.0
    else:
        stroke = 88.0
    bore = ((4.0 * per_cyl_cc * 1000.0) / (3.141592653589793 * stroke)) ** 0.5
    return float(bore), float(stroke)


def _default_target_boost(spec: WizardSpec) -> float | None:
    if spec.aspiration != "Turbo":
        return None
    if spec.objective == "spool":
        return 60.0
    if spec.objective == "efficiency":
        return 45.0
    if spec.objective == "peak_power":
        return 85.0
    return 70.0


def review_wizard_spec(spec: WizardSpec) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if int(spec.rpm_end) <= int(spec.rpm_start):
        errors.append("Target RPM end must be greater than target RPM start.")
    if spec.aspiration != "Turbo" and spec.objective == "spool":
        warnings.append("Objective 'spool' is most meaningful with a turbo setup.")
    if spec.complexity == "Basic" and any(
        value is not None
        for value in (
            spec.displacement_cc,
            spec.compression_ratio,
            spec.runner_length_mm,
            spec.header_length_mm,
            spec.runner_diameter_mm,
            spec.header_diameter_mm,
            spec.peak_rpm,
            spec.redline_rpm,
            spec.thermal_efficiency,
            spec.port_flow_efficiency,
            spec.intake_duration_deg,
            spec.exhaust_duration_deg,
            spec.intake_lift_mm,
            spec.exhaust_lift_mm,
            spec.lobe_separation_deg,
            spec.ignition_advance_deg,
            spec.target_boost_kpa,
        )
    ):
        warnings.append("Basic level ignores advanced and expert overrides and uses guided defaults.")
    if spec.complexity == "Advanced" and any(
        value is not None
        for value in (
            spec.runner_diameter_mm,
            spec.header_diameter_mm,
            spec.peak_rpm,
            spec.redline_rpm,
            spec.thermal_efficiency,
            spec.port_flow_efficiency,
            spec.intake_duration_deg,
            spec.exhaust_duration_deg,
            spec.intake_lift_mm,
            spec.exhaust_lift_mm,
            spec.lobe_separation_deg,
            spec.ignition_advance_deg,
            spec.target_boost_kpa,
        )
    ):
        warnings.append("Advanced level ignores expert-only overrides and keeps guided valvetrain and efficiency defaults.")
    return {"errors": errors, "warnings": warnings}


def _use_case_adjustments(spec: WizardSpec) -> dict[str, float]:
    if spec.use_case == "Track":
        return {"peak_rpm_mul": 1.08, "redline_add": 500.0, "compression_add": 0.3}
    if spec.use_case == "Tow":
        return {"peak_rpm_mul": 0.88, "redline_add": 0.0, "compression_add": -0.2}
    if spec.use_case == "Prototype":
        return {"peak_rpm_mul": 1.03, "redline_add": 250.0, "compression_add": 0.0}
    return {"peak_rpm_mul": 1.0, "redline_add": 0.0, "compression_add": 0.0}


def build_engine_from_wizard(spec: WizardSpec) -> Engine:
    review = review_wizard_spec(spec)
    if review["errors"]:
        raise ValueError("; ".join(review["errors"]))

    architecture = ARCHITECTURE_PRESETS.get(spec.architecture, ARCHITECTURE_PRESETS["Inline-4"])
    cylinders = int(architecture["num_cylinders"])
    complexity = spec.complexity if spec.complexity in COMPLEXITY_FIELDS else "Basic"
    advanced = complexity in {"Advanced", "Expert"}
    expert = complexity == "Expert"
    displacement_cc = float(spec.displacement_cc if advanced and spec.displacement_cc is not None else architecture["displacement_cc"])
    rpm_start = max(int(spec.rpm_start), 1000)
    rpm_end = int(spec.rpm_end)
    tuning = _use_case_adjustments(spec)
    peak_rpm = float(spec.peak_rpm if expert and spec.peak_rpm is not None else ((rpm_start + rpm_end) / 2.0) * tuning["peak_rpm_mul"])
    redline_rpm = float(spec.redline_rpm if expert and spec.redline_rpm is not None else (rpm_end + 500.0 + tuning["redline_add"]))
    bore, stroke = _bore_stroke_from_displacement(displacement_cc, cylinders, spec.objective)

    if spec.objective == "torque_mean":
        runner_length = 420.0
        runner_diameter = 42.0
        header_length = 760.0
        header_diameter = 36.0
        compression_ratio = 10.8
        thermal_efficiency = 0.50
        port_flow_efficiency = 0.68
        intake_duration = 252.0
        exhaust_duration = 256.0
        intake_lift = 10.2
        exhaust_lift = 9.8
        lsa = 112.0
    elif spec.objective == "peak_power":
        runner_length = 280.0
        runner_diameter = 50.0
        header_length = 620.0
        header_diameter = 42.0
        compression_ratio = 11.8
        thermal_efficiency = 0.54
        port_flow_efficiency = 0.78
        intake_duration = 272.0
        exhaust_duration = 270.0
        intake_lift = 11.5
        exhaust_lift = 11.0
        lsa = 108.0
    elif spec.objective == "spool":
        runner_length = 300.0
        runner_diameter = 44.0
        header_length = 500.0
        header_diameter = 34.0
        compression_ratio = 10.0
        thermal_efficiency = 0.49
        port_flow_efficiency = 0.67
        intake_duration = 248.0
        exhaust_duration = 252.0
        intake_lift = 10.0
        exhaust_lift = 9.6
        lsa = 114.0
    elif spec.objective == "efficiency":
        runner_length = 360.0
        runner_diameter = 40.0
        header_length = 700.0
        header_diameter = 35.0
        compression_ratio = 12.5
        thermal_efficiency = 0.57
        port_flow_efficiency = 0.66
        intake_duration = 242.0
        exhaust_duration = 246.0
        intake_lift = 9.2
        exhaust_lift = 8.8
        lsa = 114.0
    else:
        runner_length = 340.0
        runner_diameter = 46.0
        header_length = 850.0
        header_diameter = 38.0
        compression_ratio = 10.6
        thermal_efficiency = 0.49
        port_flow_efficiency = 0.70
        intake_duration = 260.0
        exhaust_duration = 264.0
        intake_lift = 10.5
        exhaust_lift = 10.0
        lsa = 110.0

    engine = Engine(
        model_name=f"{spec.architecture} {spec.aspiration} {OBJECTIVE_LABELS.get(spec.objective, 'Preset')}",
        block=Block(
            bore=bore,
            stroke=stroke,
            conrod_length=max(stroke * 1.65, 120.0),
            num_cylinders=cylinders,
            config=str(architecture["config"]),
            bank_angle=float(architecture["bank_angle"]),
            firing_order=list(architecture["firing_order"]),
            redline_rpm=redline_rpm,
        ),
        head=CylinderHead(
            compression_ratio=float(
                spec.compression_ratio
                if advanced and spec.compression_ratio is not None
                else compression_ratio + tuning["compression_add"]
            ),
            intake_valves=2,
            exhaust_valves=2,
            intake_valve_diameter_mm=max(bore * 0.41, 22.0),
            exhaust_valve_diameter_mm=max(bore * 0.35, 20.0),
            port_flow_cfm=max(displacement_cc / 10.0, 45.0),
            port_flow_efficiency=float(spec.port_flow_efficiency if expert and spec.port_flow_efficiency is not None else port_flow_efficiency),
            exhaust_valve_cd=0.85,
            exhaust_valve_seat_diameter_mm=max(bore * 0.35, 20.0),
            gasket_thickness_mm=1.0,
            gasket_bore_mm=max(bore + 2.0, bore),
        ),
        camshaft=Camshaft(
            intake_lift=float(spec.intake_lift_mm if expert and spec.intake_lift_mm is not None else intake_lift),
            exhaust_lift=float(spec.exhaust_lift_mm if expert and spec.exhaust_lift_mm is not None else exhaust_lift),
            intake_duration=float(spec.intake_duration_deg if expert and spec.intake_duration_deg is not None else intake_duration),
            exhaust_duration=float(spec.exhaust_duration_deg if expert and spec.exhaust_duration_deg is not None else exhaust_duration),
            lobe_separation=float(spec.lobe_separation_deg if expert and spec.lobe_separation_deg is not None else lsa),
            advance=0.0,
            peak_rpm=peak_rpm,
        ),
        intake=IntakeSystem(
            runner_length=float(spec.runner_length_mm if advanced and spec.runner_length_mm is not None else runner_length),
            runner_diameter=float(spec.runner_diameter_mm if expert and spec.runner_diameter_mm is not None else runner_diameter),
            plenum_volume=max(displacement_cc / 1000.0 * 1.4, 0.6),
            throttle_body_dia=max(((spec.runner_diameter_mm if expert and spec.runner_diameter_mm is not None else runner_diameter)) * 1.45, 38.0),
            throttle_cfm=max(displacement_cc * 0.30, 120.0),
            flow_loss_coefficient=0.02,
        ),
        exhaust=ExhaustSystem(
            header_primary_length=float(spec.header_length_mm if advanced and spec.header_length_mm is not None else header_length),
            header_primary_diameter=float(spec.header_diameter_mm if expert and spec.header_diameter_mm is not None else header_diameter),
            collector_length=max(
                (spec.header_length_mm if advanced and spec.header_length_mm is not None else header_length) * 0.85,
                250.0,
            ),
        ),
        throttle=Throttle(
            enabled=True,
            position=1.0,
            body_diam_m=max(
                (spec.runner_diameter_mm if expert and spec.runner_diameter_mm is not None else runner_diameter) * 1e-3 * 1.1,
                0.04,
            ),
            cd=0.92,
            area_exponent=2.0,
        ),
        supercharger=Supercharger(type="NA", boost_pressure_bar=0.0, intercooler_efficiency=0.7),
        turbo=Turbo(
            enabled=spec.aspiration == "Turbo",
            compressor_map=[{"pr": 1.6, "flow": 0.18, "eff": 0.72}] if spec.aspiration == "Turbo" else [],
            turbine_map=[{"pr": 1.8, "flow": 0.16, "eff": 0.70}] if spec.aspiration == "Turbo" else [],
            compressor_efficiency=0.72,
            turbine_efficiency=0.70,
            target_boost_kpa=float(spec.target_boost_kpa if expert and spec.target_boost_kpa is not None else _default_target_boost(spec) or 0.0)
            if spec.aspiration == "Turbo"
            else None,
            target_pr=1.7 if spec.aspiration == "Turbo" else None,
            intercooler_efficiency=0.72 if spec.aspiration == "Turbo" else 0.6,
        ),
        simulation_settings=SimulationSettings(
            ignition_timing_btdc=float(spec.ignition_advance_deg if expert and spec.ignition_advance_deg is not None else 28.0),
            air_temperature_c=25.0,
            air_pressure_bar=1.013,
            gamma_air=1.4,
            gamma_exhaust=1.35,
            gas_constant_R=287.0,
            cp_model="constant",
            enable_heat_transfer_1d=False,
            wall_temperature_k=450.0,
            enable_0d_to_1d_exhaust_coupling=False,
            exhaust_valve_cd=0.85,
            exhaust_valve_area_model="curtain",
            trace_metadata=True,
        ),
        friction=Friction(
            bottom_end_type="Performance" if spec.objective in {"peak_power", "spool"} else "Standard",
            friction_base_kpa=33.0 if spec.objective == "efficiency" else 36.0,
            friction_linear_factor=0.018,
            friction_quadratic_factor=1.6e-6,
            global_scaling_factor=1.0,
        ),
        combustion=Combustion(
            thermal_efficiency=float(spec.thermal_efficiency if expert and spec.thermal_efficiency is not None else thermal_efficiency),
            burn_duration=44.0 if spec.objective in {"peak_power", "spool"} else 50.0,
            ignition_advance=float(spec.ignition_advance_deg if expert and spec.ignition_advance_deg is not None else 28.0),
            afr=12.2 if spec.aspiration == "Turbo" else 13.0,
            chamber_type="Modern Pentroof",
            wiebe_a=5.0,
            wiebe_m=2.0,
        ),
    )
    return engine


def summarize_engine_for_wizard(engine: Engine, spec: WizardSpec) -> dict[str, str]:
    aspiration = "Turbo" if engine.turbo.enabled else "Naturally Aspirated"
    per_cyl = engine.block.displacement_cc / max(engine.block.num_cylinders, 1)
    bore_stroke_ratio = engine.block.bore / max(engine.block.stroke, 1e-9)
    mean_piston_speed = 2.0 * (engine.block.stroke * 1e-3) * engine.block.redline_rpm / 60.0
    return {
        "Model": engine.model_name,
        "Complexity": spec.complexity,
        "Use case": spec.use_case,
        "Architecture": spec.architecture,
        "Aspiration": aspiration,
        "Displacement": f"{engine.block.displacement_cc:.0f} cc total / {per_cyl:.0f} cc per cyl",
        "Geometry": f"{engine.block.bore:.1f} x {engine.block.stroke:.1f} mm (B/S {bore_stroke_ratio:.2f})",
        "RPM target": f"{spec.rpm_start} - {spec.rpm_end} rpm, peak {engine.camshaft.peak_rpm:.0f}, redline {engine.block.redline_rpm:.0f}",
        "Compression ratio": f"{engine.head.compression_ratio:.2f}:1",
        "Valvetrain": (
            f"Int {engine.camshaft.intake_duration:.0f}/{engine.camshaft.intake_lift:.1f}, "
            f"Exh {engine.camshaft.exhaust_duration:.0f}/{engine.camshaft.exhaust_lift:.1f}, "
            f"LSA {engine.camshaft.lobe_separation:.1f}"
        ),
        "Intake": f"Runner {engine.intake.runner_length:.0f} mm x {engine.intake.runner_diameter:.0f} mm, plenum {engine.intake.plenum_volume:.1f} L",
        "Exhaust": f"Primary {engine.exhaust.header_primary_length:.0f} mm x {engine.exhaust.header_primary_diameter:.0f} mm, collector {engine.exhaust.collector_length:.0f} mm",
        "Boost": f"{engine.turbo.target_boost_kpa:.0f} kPa target / PR {engine.turbo.target_pr:.2f}" if engine.turbo.enabled else "Naturally aspirated",
        "Efficiency model": f"Thermal eff {engine.combustion.thermal_efficiency:.2f}, port flow eff {engine.head.port_flow_efficiency:.2f}",
        "Mechanical": f"Mean piston speed at redline {mean_piston_speed:.1f} m/s",
        "Objective": OBJECTIVE_LABELS.get(spec.objective, spec.objective),
    }
