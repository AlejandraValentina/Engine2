from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.advanced.coupling import ValveTiming
from core.advanced.junctions import JunctionCapacitance, JunctionCapacitanceConfig
from core.advanced.orchestrator import (
    Orchestrator,
    OrchestratorConfig,
    PipePrefillConfig,
    PipePrefillState,
    ValveClosedWallBCConfig,
)
from core.engine_components import Engine
PRESET_PATH = ROOT / "presets" / "v2_full_features_demo.json"
OUT_PATH = Path(__file__).resolve().parent / "out_v2_demo.json"
CYCLES = 10
PIPE_CELLS = 8
RPM = 1500.0
LIFT_SCALE = 0.5
DURATION_SCALE = 0.6
LENGTH_SCALE = 0.6


def _load_engine(path: Path) -> tuple[Engine, dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    engine = Engine.from_dict(raw)
    return engine, raw


def _build_orchestrator(engine: Engine, raw: dict[str, Any], pipe_role: str) -> Orchestrator:
    prefill_cfg = raw.get("pipe_prefill", {})
    pipe_prefill = PipePrefillConfig(
        enabled=bool(prefill_cfg.get("enabled", False)),
        intake=PipePrefillState(**prefill_cfg.get("intake", {})),
        exhaust=PipePrefillState(**prefill_cfg.get("exhaust", {})),
    )
    wall_bc = ValveClosedWallBCConfig(**raw.get("valve_closed_wall_bc", {}))
    cfg = OrchestratorConfig(
        cp_model=engine.simulation_settings.cp_model,
        pipe_role=pipe_role,
        throttle=engine.throttle,
        pipe_prefill=pipe_prefill,
        valve_closed_wall_bc=wall_bc,
        max_cycles=CYCLES,
        dt_max=1e-4,
        convergence_tol=0.0,
        periodicity_tol=0.0,
        periodicity_required=CYCLES + 1,
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


def _run_single_pipe(
    engine: Engine,
    raw: dict[str, Any],
    pipe_role: str,
    pipe_length_m: float,
    pipe_diameter_m: float,
    junction_totals: tuple[float, float, float] | None,
) -> dict[str, Any]:
    orchestrator = _build_orchestrator(engine, raw, pipe_role)
    valve = _build_valve(engine, pipe_role)

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
        junction_totals=junction_totals,
    )

    disp_m3 = area * stroke_m
    indicated_work = result["indicated_work"][-1] if result["indicated_work"] else 0.0
    imep = indicated_work / max(disp_m3, 1e-12)
    trapped = result["trapped_mass"][-1] if result["trapped_mass"] else 0.0
    history = result.get("convergence_history", [])
    return {
        "pipe_role": pipe_role,
        "imep": float(imep),
        "trapped_mass": float(trapped),
        "convergence_history": history,
    }


def _load_junction_totals(raw: dict[str, Any], engine: Engine) -> tuple[float, float, float] | None:
    junctions = raw.get("junctions", {})
    if not junctions:
        return None
    first = next(iter(junctions.values()))
    cap = first.get("capacitance")
    if not isinstance(cap, dict):
        return None
    config = JunctionCapacitanceConfig.from_dict(cap)
    if not config.enabled:
        return None
    p_init = float(first.get("pressure", 101325.0))
    T_init = float(first.get("temperature", 700.0))
    Y_init = 0.0
    node = JunctionCapacitance(
        config,
        gamma=1.35,
        gas_constant=engine.simulation_settings.gas_constant_R,
        cp=engine.simulation_settings.gamma_exhaust * engine.simulation_settings.gas_constant_R
        / max(engine.simulation_settings.gamma_exhaust - 1.0, 1e-9),
        p_init=p_init,
        T_init=T_init,
        Y_init=Y_init,
    )
    return node.totals()


def main() -> None:
    engine, raw = _load_engine(PRESET_PATH)

    intake_len_m = engine.intake.runner_length * 1e-3 * LENGTH_SCALE
    intake_d_m = engine.intake.runner_diameter * 1e-3
    exhaust_len_m = engine.exhaust.header_primary_length * 1e-3 * LENGTH_SCALE
    exhaust_d_m = engine.exhaust.header_primary_diameter * 1e-3

    junction_totals = _load_junction_totals(raw, engine)

    intake = _run_single_pipe(
        engine,
        raw,
        "intake",
        intake_len_m,
        intake_d_m,
        None,
    )
    exhaust = _run_single_pipe(
        engine,
        raw,
        "exhaust",
        exhaust_len_m,
        exhaust_d_m,
        junction_totals,
    )

    print("=== v2 Full Features Demo ===")
    for label, data in (("intake", intake), ("exhaust", exhaust)):
        print(f"{label} IMEP: {data['imep']:.2f} Pa")
        print(f"{label} trapped mass: {data['trapped_mass']:.6f} kg")
        tail = data["convergence_history"][-5:]
        print(f"{label} convergence tail:")
        for entry in tail:
            print(entry)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps({"intake": intake, "exhaust": exhaust}, indent=2),
        encoding="utf-8",
    )
    print(f"Saved results to {OUT_PATH}")


if __name__ == "__main__":
    main()
