from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Iterable

import numpy as np

from core.engine_components import Engine, Pipe
from core.thermo import CylinderSimulator
from core.simulator import Engine1DSolver
from core.wave_utils import build_exhaust_coupling, compute_pressure_matrix


def _git_version() -> str:
    try:
        return (
            subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL)
            .decode("utf-8")
            .strip()
        )
    except Exception:
        return "unknown"


def _load_engine(path: Path) -> tuple[Engine, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    normalized = json.dumps(raw, sort_keys=True).encode("utf-8")
    engine = Engine.from_dict(raw)
    return engine, raw


def _input_hash(raw: dict) -> str:
    payload = json.dumps(raw, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _parse_rpm_range(value: str) -> list[float]:
    if ":" in value:
        start_s, end_s, step_s = value.split(":")
        start = float(start_s)
        end = float(end_s)
        step = float(step_s)
        if step <= 0:
            raise ValueError("RPM step must be positive")
        return [float(v) for v in np.arange(start, end + 0.1 * step, step)]
    return [float(value)]


def _metadata(engine: Engine, raw: dict, coupling_mode: str) -> dict:
    return {
        "input_hash": _input_hash(raw),
        "timestamp": dt.datetime.utcnow().isoformat() + "Z",
        "version": _git_version(),
        "settings": engine.simulation_settings.to_dict(),
        "coupling_mode": coupling_mode,
    }


def _build_wave_solver(engine: Engine) -> Engine1DSolver:
    exhaust = engine.exhaust
    block = engine.block

    n_cyl = max(block.num_cylinders, 1)
    primaries: list[Pipe] = []
    for _ in range(n_cyl):
        primaries.append(
            Pipe(
                length=exhaust.header_primary_length,
                diameter_inlet=exhaust.header_primary_diameter,
                diameter_outlet=exhaust.header_primary_diameter,
                wall_temperature=600.0,
                friction_coeff=0.02,
            )
        )

    collector_area = np.pi * (exhaust.header_primary_diameter * 1e-3 * 0.5) ** 2
    collector_volume = max(collector_area * 0.1 * n_cyl, 1e-4)

    tail_dia = exhaust.header_primary_diameter * max(np.sqrt(n_cyl) * 0.6, 1.2)
    tailpipe = Pipe(
        length=exhaust.collector_length,
        diameter_inlet=tail_dia,
        diameter_outlet=tail_dia,
        wall_temperature=600.0,
        friction_coeff=0.02,
    )

    return Engine1DSolver(
        primaries,
        tailpipe,
        block.firing_order,
        collector_volume=collector_volume,
        settings=engine.simulation_settings,
        camshaft=engine.camshaft,
        head=engine.head,
    )


def run_dyno(engine_path: Path, rpm_spec: str, out_path: Path) -> None:
    engine, raw = _load_engine(engine_path)
    simulator = CylinderSimulator(engine)
    rpm_values = _parse_rpm_range(rpm_spec)
    results = []
    for rpm in rpm_values:
        cycle = simulator.run_cycle(rpm)
        results.append(
            {
                "rpm": rpm,
                "mean_power_hp": float(cycle["mean_power_hp"]),
                "mean_torque_nm": float(cycle["mean_torque_nm"]),
                "bmep_bar": float(cycle["bmep_bar"]),
                "ve_actual": float(cycle["ve_actual"]),
            }
        )

    output = {
        "metadata": _metadata(engine, raw, coupling_mode="none"),
        "results": results,
    }
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


def run_scope(engine_path: Path, rpm: float, cycles: int, out_path: Path) -> None:
    engine, raw = _load_engine(engine_path)
    simulator = CylinderSimulator(engine)
    solver = _build_wave_solver(engine)

    coupling_mode = "none"
    coupling_data = None
    if engine.simulation_settings.enable_0d_to_1d_exhaust_coupling:
        cycle = simulator.run_cycle(rpm)
        coupling_data = build_exhaust_coupling(
            cycle["angle"],
            cycle["exhaust_p_stag"],
            cycle["exhaust_t_stag"],
            engine.block.firing_order,
        )
        coupling_mode = "0d_to_1d_exhaust"

    history, audio, time_vector = solver.run_full_simulation(
        rpm,
        cycles=cycles,
        coupling_data=coupling_data,
    )
    matrix = compute_pressure_matrix(history, solver.gamma)
    output = {
        "metadata": _metadata(engine, raw, coupling_mode=coupling_mode),
        "time": list(time_vector),
        "tail_pressure_pa": list(audio),
        "pressure_matrix_pa": matrix.tolist(),
    }
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pywavedyn.cli", description="PyWaveDyn headless CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    dyno = sub.add_parser("dyno", help="Run a 0D dyno sweep")
    dyno.add_argument("--engine", required=True, type=Path)
    dyno.add_argument("--rpm", required=True, help="RPM or range start:end:step")
    dyno.add_argument("--out", required=True, type=Path)

    scope = sub.add_parser("scope", help="Run a 1D wave scope")
    scope.add_argument("--engine", required=True, type=Path)
    scope.add_argument("--rpm", required=True, type=float)
    scope.add_argument("--cycles", type=int, default=2)
    scope.add_argument("--out", required=True, type=Path)

    return parser


def main(argv: Iterable[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "dyno":
        run_dyno(args.engine, args.rpm, args.out)
    elif args.command == "scope":
        run_scope(args.engine, args.rpm, args.cycles, args.out)


if __name__ == "__main__":
    main()
