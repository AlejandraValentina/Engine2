from __future__ import annotations

import json
import math
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.advanced.coupling import ValveTiming
from core.advanced.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    PipePrefillConfig,
    PipePrefillState,
    ValveClosedWallBCConfig,
)
from core.advanced.plenum_cv import ExhaustPlenumConfig, IntakePlenumConfig
from core.engine_components import Engine

PRESET_PATH = ROOT / "presets" / "v2_full_features_demo.json"
OUT_PATH = ROOT / "out_v2_demo.json"
CYCLES = 10
PIPE_CELLS = 8
RPM = 1500.0
LIFT_SCALE = 0.5
DURATION_SCALE = 0.6
LENGTH_SCALE = 0.6
PART_THROTTLE = 0.6


def _load_engine(path: Path) -> tuple[Engine, dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    engine = Engine.from_dict(raw)
    return engine, raw


def _build_orchestrator(
    engine: Engine,
    raw: dict[str, Any],
    pipe_role: str,
    throttle_position: float,
) -> Orchestrator:
    prefill_cfg = raw.get("pipe_prefill", {})
    amb_p_pa = float(engine.simulation_settings.air_pressure_bar) * 100000.0
    amb_T_k = float(engine.simulation_settings.air_temperature_c) + 273.15
    exhaust_prefill_T = prefill_cfg.get("exhaust_prefill_T_K", prefill_cfg.get("exhaust_prefill_T", 700.0))
    pipe_prefill = PipePrefillConfig(
        enabled=bool(prefill_cfg.get("enabled", False)),
        auto=bool(prefill_cfg.get("auto", False)),
        auto_amb_p_Pa=float(prefill_cfg.get("auto_amb_p_Pa", amb_p_pa)),
        auto_amb_T_K=float(prefill_cfg.get("auto_amb_T_K", amb_T_k)),
        exhaust_prefill_T_K=float(exhaust_prefill_T),
        intake=PipePrefillState(**prefill_cfg.get("intake", {})),
        exhaust=PipePrefillState(**prefill_cfg.get("exhaust", {})),
    )
    wall_bc = ValveClosedWallBCConfig(**raw.get("valve_closed_wall_bc", {}))
    sim_intake_plenum = getattr(engine.simulation_settings, "intake_plenum", {})
    sim_exhaust_plenum = getattr(engine.simulation_settings, "exhaust_plenum", {})
    intake_plenum = IntakePlenumConfig.from_dict(sim_intake_plenum or raw.get("intake_plenum", {}))
    exhaust_plenum = ExhaustPlenumConfig.from_dict(sim_exhaust_plenum or raw.get("exhaust_plenum", {}))
    enable_pumping_work = bool(raw.get("enable_pumping_work", False))

    throttle_cfg = deepcopy(engine.throttle)
    throttle_cfg.position = throttle_position

    cfg = OrchestratorConfig(
        cp_model=engine.simulation_settings.cp_model,
        pipe_role=pipe_role,
        throttle=throttle_cfg,
        pipe_prefill=pipe_prefill,
        valve_closed_wall_bc=wall_bc,
        max_cycles=CYCLES,
        dt_max=1e-4,
        convergence_tol=0.0,
        periodicity_tol=0.0,
        periodicity_required=CYCLES + 1,
        fuel=engine.simulation_settings.fuel,
        intake_plenum=intake_plenum,
        exhaust_plenum=exhaust_plenum,
        enable_pumping_work=enable_pumping_work,
    )
    return Orchestrator(cfg)


def _build_valve(engine: Engine, kind: str) -> ValveTiming:
    if kind == "intake":
        lift_m = engine.camshaft.intake_lift * 1e-3 * LIFT_SCALE
        seat_mm = engine.head.intake_valve_diameter
        open_start = 0.0
        open_end = max(engine.camshaft.intake_duration * DURATION_SCALE, 1.0)
    else:
        lift_m = engine.camshaft.exhaust_lift * 1e-3 * LIFT_SCALE
        seat_mm = engine.head.exhaust_valve_seat_diameter_mm or engine.head.exhaust_valve_diameter
        open_start = 360.0
        open_end = open_start + max(engine.camshaft.exhaust_duration * DURATION_SCALE, 1.0)
    return ValveTiming(
        open_start_deg=open_start,
        open_end_deg=open_end,
        max_lift_m=lift_m,
        seat_diameter_m=seat_mm * 1e-3,
        cd=0.9,
    )


def _run_case(engine: Engine, raw: dict[str, Any], throttle_position: float) -> dict[str, Any]:
    orchestrator = _build_orchestrator(engine, raw, "intake", throttle_position)
    valve = _build_valve(engine, "intake")

    pipe_length_m = engine.intake.runner_length * 1e-3 * LENGTH_SCALE
    pipe_diameter_m = engine.intake.runner_diameter * 1e-3

    bore_m = engine.block.bore * 1e-3
    stroke_m = engine.block.stroke * 1e-3
    conrod_m = engine.block.conrod_length * 1e-3
    area = math.pi * (bore_m * 0.5) ** 2
    clearance_m3 = area * stroke_m / max(engine.head.compression_ratio - 1.0, 1e-6)

    result = orchestrator.run(
        rpm=RPM,
        pipe_cells=PIPE_CELLS,
        pipe_length_m=pipe_length_m,
        pipe_diameter_m=pipe_diameter_m,
        bore_m=bore_m,
        stroke_m=stroke_m,
        conrod_m=conrod_m,
        clearance_m3=clearance_m3,
        valve=valve,
    )

    disp_m3 = area * stroke_m
    indicated_work = result["indicated_work"][-1] if result["indicated_work"] else 0.0
    imep = indicated_work / max(disp_m3, 1e-12)
    trapped = result["trapped_mass"][-1] if result["trapped_mass"] else 0.0
    periodicity = result.get("periodicity_metric", [])
    periodicity_error = periodicity[-1] if periodicity else None

    bsfc = None
    fuel_tail = result.get("fuel_metrics", [])
    if fuel_tail:
        bsfc = fuel_tail[-1].get("bsfc_g_per_kwh")

    pumping_work = None
    pumping_hist = result.get("pumping_work", [])
    if pumping_hist:
        pumping_work = pumping_hist[-1]

    return {
        "rpm": float(RPM),
        "throttle_position": float(throttle_position),
        "imep": float(imep),
        "trapped_mass": float(trapped),
        "periodicity_error": float(periodicity_error) if periodicity_error is not None else None,
        "bsfc_g_per_kwh": float(bsfc) if bsfc is not None else None,
        "pumping_work": float(pumping_work) if pumping_work is not None else None,
        "result": result,
    }


def _format_line(label: str, summary: dict[str, Any]) -> str:
    imep = summary.get("imep")
    trapped = summary.get("trapped_mass")
    periodicity = summary.get("periodicity_error")
    bsfc = summary.get("bsfc_g_per_kwh")
    pumping_work = summary.get("pumping_work")

    periodicity_str = f"{periodicity:.3e}" if periodicity is not None else "n/a"
    line = (
        f"{label}: RPM={summary['rpm']:.0f}, IMEP={imep:.2f} Pa, "
        f"trapped_mass={trapped:.6f} kg, periodicity_error={periodicity_str}"
    )
    if bsfc is not None:
        line += f", BSFC={bsfc:.2f} g/kWh"
    if pumping_work is not None:
        line += f", pumping_work={pumping_work:.2f} J"
    return line


def main() -> None:
    engine, raw = _load_engine(PRESET_PATH)

    cases = [
        ("WOT", 1.0),
        ("PartThrottle", PART_THROTTLE),
    ]

    results: dict[str, Any] = {}
    print("=== v2 Full Features Demo ===")
    for label, throttle_position in cases:
        summary = _run_case(engine, raw, throttle_position)
        results[label] = summary
        print(_format_line(label, summary))

    OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved results to {OUT_PATH}")


if __name__ == "__main__":
    main()
