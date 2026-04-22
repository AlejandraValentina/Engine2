from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

from acoustics.audio_generator import (
    save_multicylinder_wav,
    render_pressure_trace,
    mix_multicylinder_from_trace,
    _smooth_waveform,
)
from core.engine_components import Engine, Pipe
from core.bmep_calibrator import calibrate_bmep
from core.knock import KnockConfig, compute_knock_index
from core.legacy_compat import LEGACY_PROFILE_V1, apply_legacy_compat
from core.pro_dyno_v2 import ProDynoV2Runner
from core.thermo import CylinderSimulator
from core.simulator import Engine1DSolver
from core.intake_scope import run_intake_scope as run_intake_scope_sim
from core.map_runner import run_partload_map
from core.auto_calibration import calibrate_engine, calibrate_engine_diagnostics
from core.optimize_runner import load_target_points, optimize_guided, optimize_runner_length
from pywavedyn.bench import evaluate_with_engine
from pywavedyn.bench_import import parse_mapping_text, parse_units_text, write_dataset_package
from pywavedyn.calibrate import run_reproducible_calibration
from pywavedyn.analysis_contract import (
    OBSERVABLE_VE_ACTUAL,
    REPORT_TYPE_COMPARE,
    REPORT_TYPE_OPTIMIZE_GUIDED,
    REPORT_TYPE_SENSITIVITY_LOCAL,
    REPORT_TYPE_STAGED_CALIBRATION,
    apply_analysis_envelope,
    apply_observable_semantics,
    build_report_context,
    dataset_context_from_dir,
)
from pywavedyn.combustion_mode import apply_adaptive_combustion_mode
from pywavedyn.dyno_data import write_dataset_package as write_flexible_dataset_package
from pywavedyn.engineering_diagnostics import diagnose_dyno_output
from pywavedyn.staged_calibration import run_staged_calibration
from pywavedyn.ab_sensitivity import run_ab_compare, run_local_sensitivity
from pywavedyn.validation_compare import apply_turbo_incremental_mode, run_validation_batch
from core.full_network import run_full_scope as run_full_scope_sim
from core.units import cc_to_m3
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


def _resolve_legacy_profile(
    path: Path, raw: dict, legacy_compat: str | None, auto_legacy_compat: bool
) -> str | None:
    if legacy_compat:
        return legacy_compat
    meta = raw.get("meta", {}) if isinstance(raw.get("meta", {}), dict) else {}
    legacy_meta = meta.get("legacy_compat")
    if legacy_meta is True:
        return LEGACY_PROFILE_V1
    if isinstance(legacy_meta, str) and legacy_meta.lower() in {"v1", "legacy_v1"}:
        return LEGACY_PROFILE_V1
    if auto_legacy_compat:
        parts = [part.lower() for part in path.parts]
        if "presets" in parts and "legacy" in parts:
            return LEGACY_PROFILE_V1
    return None


def _load_engine_with_legacy(
    path: Path,
    *,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> tuple[Engine, dict, str | None, dict | None]:
    engine, raw = _load_engine(path)
    profile = _resolve_legacy_profile(path, raw, legacy_compat, auto_legacy_compat)
    overrides = None
    if profile:
        overrides = apply_legacy_compat(raw, engine, profile=profile)
    return engine, raw, profile, overrides


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


def _parse_firing_order(value: str) -> list[int]:
    if not value:
        return []
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return [int(p) for p in parts]


def _parse_length_list(value: str) -> list[float]:
    if not value:
        return []
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return [float(p) for p in parts]


def _parse_float_list(value: str) -> list[float]:
    if not value:
        return []
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return [float(p) for p in parts]


def _parse_path_list(values: Sequence[Path] | Sequence[str]) -> list[Path]:
    return [Path(value) for value in values]


def _parse_float_mapping_text(value: str) -> dict[str, float]:
    if not value:
        return {}
    mapping: dict[str, float] = {}
    for item in str(value).split(","):
        chunk = item.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(f"mapping entry must be key=value, got '{chunk}'")
        key, raw = chunk.split("=", 1)
        mapping[key.strip()] = float(raw.strip())
    return mapping


def _parse_bounds_map_text(value: str) -> dict[str, tuple[float, float]]:
    if not value:
        return {}
    mapping: dict[str, tuple[float, float]] = {}
    for item in str(value).split(","):
        chunk = item.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError(f"bounds entry must be param=low:high, got '{chunk}'")
        key, raw = chunk.split("=", 1)
        if ":" not in raw:
            raise ValueError(f"bounds entry must be param=low:high, got '{chunk}'")
        low_s, high_s = raw.split(":", 1)
        mapping[key.strip()] = (float(low_s.strip()), float(high_s.strip()))
    return mapping


def _parse_numeric_range(value: str, *, default_step: float = 1.0) -> list[float]:
    if not value:
        return []
    if ":" in value:
        parts = [p.strip() for p in value.split(":") if p.strip()]
        if len(parts) == 2:
            start_s, end_s = parts
            step = float(default_step)
        elif len(parts) == 3:
            start_s, end_s, step_s = parts
            step = float(step_s)
        else:
            raise ValueError("range must be formatted as start:end[:step]")
        start = float(start_s)
        end = float(end_s)
        if step <= 0:
            raise ValueError("range step must be positive")
        return [float(v) for v in np.arange(start, end + 0.1 * step, step)]
    return _parse_float_list(value)


def _parse_bounds(value: str) -> tuple[float, float]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) != 2:
        raise ValueError("bounds must be formatted as low,high")
    return float(parts[0]), float(parts[1])


def _add_legacy_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--legacy-compat",
        choices=[LEGACY_PROFILE_V1],
        default=None,
        help="Apply legacy compatibility profile (opt-in).",
    )
    parser.add_argument(
        "--auto-legacy-compat",
        action="store_true",
        help="Auto-apply legacy profile for presets/legacy (opt-in).",
    )


def _add_adaptive_combustion_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--adaptive-combustion",
        choices=["as_is", "on", "off"],
        default="as_is",
        help="Override combustion.adaptive_model.enabled for this run without editing the preset.",
    )


def _add_turbo_incremental_arg(parser: argparse.ArgumentParser, *, dest: str = "turbo_incremental") -> None:
    parser.add_argument(
        f"--{dest.replace('_', '-')}",
        dest=dest,
        choices=["as_is", "on", "off"],
        default="as_is",
        help="Override turbo.response_model.enabled for this run without editing the preset.",
    )


def _runner_length_grid(base_mm: float, points: int, span_mm: float) -> list[float]:
    points = max(int(points), 1)
    span_mm = max(float(span_mm), 0.0)
    if points == 1 or span_mm == 0.0:
        return [float(base_mm)]
    start = max(10.0, float(base_mm) - span_mm * 0.5)
    end = float(base_mm) + span_mm * 0.5
    return [float(v) for v in np.linspace(start, end, points)]


def _metadata(
    engine: Engine,
    raw: dict,
    coupling_mode: str,
    *,
    legacy_compat: str | None = None,
    legacy_overrides: dict | None = None,
) -> dict:
    payload = {
        "input_hash": _input_hash(raw),
        "timestamp": dt.datetime.utcnow().isoformat() + "Z",
        "version": _git_version(),
        "settings": engine.simulation_settings.to_dict(),
        "coupling_mode": coupling_mode,
    }
    if legacy_compat:
        payload["legacy_compat"] = legacy_compat
    if legacy_overrides:
        payload["legacy_overrides"] = legacy_overrides
    return payload


def _run_preflight(engine: Engine, *, operation: str, mode: str = "v1") -> None:
    review = engine.preflight_review(operation=operation, mode=mode)
    if not review["errors"]:
        return
    issue_text = "\n".join(f"- {issue}" for issue in review["errors"])
    raise ValueError(f"Preflight validation failed for {operation}:\n{issue_text}")


def _build_wave_solver(engine: Engine, target_dx: float | None = None) -> Engine1DSolver:
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

    kwargs = {}
    if target_dx is not None:
        kwargs["target_dx"] = float(target_dx)
    return Engine1DSolver(
        primaries,
        tailpipe,
        block.firing_order,
        collector_volume=collector_volume,
        settings=engine.simulation_settings,
        camshaft=engine.camshaft,
        head=engine.head,
        **kwargs,
    )


def _dyno_results_v1(engine: Engine, rpm_values: list[float]) -> list[dict]:
    simulator = CylinderSimulator(engine)
    results = []
    for rpm in rpm_values:
        cycle = simulator.run_cycle(rpm)
        entry = {
            "rpm": float(rpm),
            "mean_power_hp": float(cycle["mean_power_hp"]),
            "mean_torque_nm": float(cycle["mean_torque_nm"]),
            "bmep_bar": float(cycle["bmep_bar"]),
            "ve_actual": float(cycle["ve_actual"]),
        }
        for key in (
            "map_est_kpa",
            "overlap_flow_kg",
            "residual_fraction_est",
            "scavenging_index",
            "boost_kpa",
            "pr_comp",
            "pr_turb",
            "wg_duty",
            "knock_penalty_pct",
        ):
            if key in cycle:
                entry[key] = float(cycle[key])
        if "knock_warning" in cycle:
            entry["knock_warning"] = bool(cycle["knock_warning"])
        results.append(entry)
    return results


def _dyno_results_v2(engine: Engine, rpm_values: list[float], v2_settings: dict | None = None) -> list[dict]:
    runner = ProDynoV2Runner(engine, settings=v2_settings)
    rpm_ints = [int(round(rpm)) for rpm in rpm_values]
    sweep = runner.run_sweep(rpm_ints)
    rpm_series = sweep.get("rpm", rpm_ints)

    displacement_m3 = max(cc_to_m3(engine.block.displacement_cc), 1e-9)
    results = []
    status_series = sweep.get("status")
    periodicity_series = sweep.get("periodicity_error")
    reason_series = sweep.get("reason")
    for idx, rpm in enumerate(rpm_series):
        mean_power_hp = float(sweep["mean_power_hp"][idx])
        mean_torque_nm = float(sweep["mean_torque_nm"][idx])
        bmep_bar = mean_torque_nm * 4.0 * math.pi / displacement_m3 / 100000.0
        ve_actual = float(sweep["ve_real"][idx])
        entry = {
            "rpm": float(rpm),
            "mean_power_hp": mean_power_hp,
            "mean_torque_nm": mean_torque_nm,
            "bmep_bar": float(bmep_bar),
            "ve_actual": ve_actual,
        }
        if status_series is not None and idx < len(status_series):
            entry["status"] = status_series[idx]
        if periodicity_series is not None and idx < len(periodicity_series):
            entry["periodicity_error"] = periodicity_series[idx]
        if reason_series is not None and idx < len(reason_series):
            entry["reason"] = reason_series[idx]
        results.append(entry)
    return results


def _warn_knock_penalties(results: list[dict]) -> None:
    for entry in results:
        pct = entry.get("knock_penalty_pct", 0.0)
        if pct > 0:
            rpm = entry.get("rpm", "?")
            print(
                f"WARNING: knock penalty {pct}% at {rpm} RPM",
                file=sys.stderr,
            )


def _build_knock_report(
    engine: Engine,
    raw: dict,
    rpm_values: list[float],
    coupling_mode: str,
    *,
    legacy_compat: str | None = None,
    legacy_overrides: dict | None = None,
) -> dict:
    residual_cfg = getattr(engine.combustion, "residual_coupling", {}) or {}
    if not bool(residual_cfg.get("enabled", False)):
        raise ValueError("knock report requires combustion.residual_coupling.enabled = true")

    knock_cfg = residual_cfg.get("knock", {})
    if not isinstance(knock_cfg, dict):
        knock_cfg = {}

    simulator = CylinderSimulator(engine)
    results: list[dict[str, float | bool]] = []
    for rpm in rpm_values:
        cycle = simulator.run_cycle(float(rpm))
        trace = cycle.get("trace", {})
        residual_fraction = float(trace.get("residual_fraction_est", 0.0))
        start_angle = float(trace.get("start_angle_used", 360.0 - engine.combustion.ignition_advance))
        entry = compute_knock_index(
            cycle["angle"],
            cycle["temperature"],
            float(rpm),
            start_angle,
            residual_fraction,
            config=knock_cfg,
        )
        entry["rpm"] = float(rpm)
        results.append(entry)

    knock_model = KnockConfig.from_dict(knock_cfg)
    metadata = _metadata(
        engine,
        raw,
        coupling_mode=coupling_mode,
        legacy_compat=legacy_compat,
        legacy_overrides=legacy_overrides,
    )
    metadata["knock_model"] = {
        "A": knock_model.A,
        "B": knock_model.B,
        "threshold": knock_model.threshold,
        "window_deg": knock_model.window_deg,
        "residual_hot_k": knock_model.residual_hot_k,
    }
    return {"metadata": metadata, "results": results}


def run_dyno(
    engine_path: Path,
    rpm_spec: str,
    out_path: Path,
    mode: str = "v1",
    turbo_path: Path | None = None,
    settle_cycles: int = 0,
    min_periodicity: float | None = None,
    drop_invalid: bool = False,
    rpm_start_safe: bool = False,
    debug_dyno_v2: bool = False,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
    knock_report: Path | None = None,
    adaptive_combustion: str = "as_is",
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    if turbo_path is not None:
        turbo_raw = json.loads(turbo_path.read_text(encoding="utf-8"))
        engine.turbo = engine.turbo.from_dict(turbo_raw)
    engine, raw, combustion_summary = apply_adaptive_combustion_mode(
        engine,
        raw,
        mode=adaptive_combustion,
    )
    _run_preflight(engine, operation="dyno", mode=mode)
    rpm_values = _parse_rpm_range(rpm_spec)
    if mode == "v1":
        results = _dyno_results_v1(engine, rpm_values)
        coupling_mode = "none"
    elif mode == "v2":
        v2_settings: dict[str, Any] = {}
        if settle_cycles:
            v2_settings["settle_cycles"] = int(settle_cycles)
        if min_periodicity is not None:
            v2_settings["min_periodicity"] = float(min_periodicity)
            v2_settings["report_status"] = True
        if drop_invalid:
            v2_settings["drop_invalid"] = True
            v2_settings["report_status"] = True
        if rpm_start_safe:
            v2_settings["rpm_start_safe"] = True
        if debug_dyno_v2:
            v2_settings["debug_dyno_v2"] = True
        results = _dyno_results_v2(engine, rpm_values, v2_settings=v2_settings)
        coupling_mode = "v2_orchestrator"
    else:
        raise ValueError(f"Unknown mode '{mode}' (expected 'v1' or 'v2')")

    metadata = _metadata(
        engine,
        raw,
        coupling_mode=coupling_mode,
        legacy_compat=legacy_profile,
        legacy_overrides=legacy_overrides,
    )
    if mode == "v2" and (settle_cycles or min_periodicity is not None or drop_invalid or rpm_start_safe):
        metadata["dyno_v2_settings"] = {
            "settle_cycles": int(settle_cycles),
            "min_periodicity": float(min_periodicity) if min_periodicity is not None else None,
            "drop_invalid": bool(drop_invalid),
            "rpm_start_safe": bool(rpm_start_safe),
        }
    metadata["combustion"] = combustion_summary
    output = {"metadata": metadata, "results": results}
    apply_observable_semantics(output, OBSERVABLE_VE_ACTUAL)
    output["diagnostics"] = diagnose_dyno_output(output, engine=engine)
    _write_json(out_path, output)
    _warn_knock_penalties(results)

    if knock_report is not None:
        report = _build_knock_report(
            engine,
            raw,
            rpm_values,
            coupling_mode=coupling_mode,
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        )
        _write_json(knock_report, report)


def run_scope(
    engine_path: Path,
    rpm: float,
    cycles: int,
    out_path: Path,
    target_dx: float | None = None,
    max_steps: int | None = None,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    _run_preflight(engine, operation="scope", mode="v1")
    simulator = CylinderSimulator(engine)
    solver = _build_wave_solver(engine, target_dx=target_dx)

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

    if max_steps is not None and max_steps > 0:
        for state in solver.primary_states:
            state["U"] = state["initial"].copy()
        solver.tail_state["U"] = solver.tail_state["initial"].copy()
        solver.time = 0.0

        history = []
        audio = []
        time_vector = []

        for _ in range(int(max_steps)):
            dt = solver.get_time_step()
            p_stag_by_cyl = None
            t_stag_by_cyl = None
            if engine.simulation_settings.enable_0d_to_1d_exhaust_coupling:
                if coupling_data is None:
                    raise ValueError("0D->1D exhaust coupling enabled but no coupling data provided")
                p_stag_by_cyl = {}
                t_stag_by_cyl = {}
                base_angle = (solver.time * rpm * 6.0) % 720.0
                for cyl_id in range(1, solver.n_cyl + 1):
                    data = coupling_data.get(cyl_id)
                    if data is None:
                        raise ValueError(f"Missing coupling data for cylinder {cyl_id}")
                    cyl_angle = (base_angle + solver.phase_map.get(cyl_id, 0.0)) % 720.0
                    angle_arr = data["angle"]
                    p_arr = data["p_stag"]
                    t_arr = data["t_stag"]
                    p_stag_by_cyl[cyl_id] = float(np.interp(cyl_angle, angle_arr, p_arr))
                    t_stag_by_cyl[cyl_id] = float(np.interp(cyl_angle, angle_arr, t_arr))

            solver.step(rpm=rpm, dt=dt, p_stag_by_cyl=p_stag_by_cyl, T_stag_by_cyl=t_stag_by_cyl)
            history.append(solver.primary_states[0]["U"].copy())
            p_grid = (solver.gamma - 1.0) * (
                solver.tail_state["U"][:, 2]
                - 0.5 * (solver.tail_state["U"][:, 1] ** 2) / solver.tail_state["U"][:, 0]
            )
            audio.append(float(p_grid[-1]))
            time_vector.append(solver.time)
    else:
        history, audio, time_vector = solver.run_full_simulation(
            rpm,
            cycles=cycles,
            coupling_data=coupling_data,
        )
    matrix = compute_pressure_matrix(history, solver.gamma)
    output = {
        "metadata": _metadata(
            engine,
            raw,
            coupling_mode=coupling_mode,
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        ),
        "time": list(time_vector),
        "tail_pressure_pa": list(audio),
        "pressure_matrix_pa": matrix.tolist(),
    }
    _write_json(out_path, output)


def run_intake_scope(
    engine_path: Path,
    out_path: Path,
    *,
    max_steps: int | None = None,
    target_dx: float | None = None,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    result = run_intake_scope_sim(engine, max_steps=max_steps, target_dx=target_dx)
    output = {
        "metadata": _metadata(
            engine,
            raw,
            coupling_mode="intake_scope",
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        ),
        "time": result.time_s,
        "plenum_pressure_pa": result.plenum_pressure_pa,
        "runner_pressure_pa": result.runner_pressure_pa,
        "valve_area_m2": result.valve_area_m2,
    }
    _write_json(out_path, output)


def run_audio(
    engine_path: Path,
    rpm: float,
    duration: float,
    sample_rate: int,
    out_path: Path,
    firing_order: str | None,
    source: str = "runner",
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, _raw, _legacy_profile, _legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    order = _parse_firing_order(firing_order or "")
    if not order:
        order = list(engine.block.firing_order)
    if source == "runner":
        save_multicylinder_wav(
            engine,
            rpm=rpm,
            firing_order=order,
            duration=duration,
            sample_rate=sample_rate,
            filename=out_path,
        )
        return

    times, pressures = _collect_audio_trace(engine, rpm, duration, source)
    base_wave = render_pressure_trace(times, pressures, sample_rate)
    if base_wave is None or base_wave.size == 0:
        raise ValueError("Audio source produced empty waveform")
    if source == "exhaust_plenum":
        base_wave = _smooth_waveform(base_wave, window=7)
    waveform = mix_multicylinder_from_trace(
        base_wave,
        rpm=rpm,
        firing_order=order,
        duration=duration,
        sample_rate=sample_rate,
    )
    if waveform.size == 0:
        raise ValueError("Audio mixing produced empty waveform")
    from scipy.io import wavfile

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wavfile.write(out_path, int(sample_rate), waveform.astype(np.float32))


def _collect_audio_trace(engine: Engine, rpm: float, duration: float, source: str) -> tuple[list[float], list[float]]:
    if source not in ("primary", "exhaust_plenum"):
        raise ValueError(f"Unsupported audio source '{source}'")

    simulator = CylinderSimulator(engine)
    solver = _build_wave_solver(engine, target_dx=0.05)
    coupling_data = None
    if engine.simulation_settings.enable_0d_to_1d_exhaust_coupling:
        cycle = simulator.run_cycle(rpm)
        coupling_data = build_exhaust_coupling(
            cycle["angle"],
            cycle["exhaust_p_stag"],
            cycle["exhaust_t_stag"],
            engine.block.firing_order,
        )

    total_time = max(float(duration), 0.01)
    capture_time = min(total_time, 120.0 / max(float(rpm), 1.0))
    dt_est = max(float(solver.get_time_step()), 1e-6)
    max_steps = max(int(capture_time / dt_est) + 200, 200)
    max_steps = min(max_steps, 2_000_000)
    times: list[float] = []
    pressures: list[float] = []

    for _ in range(max_steps):
        if solver.time >= capture_time:
            break
        dt = solver.get_time_step()
        p_stag_by_cyl = None
        t_stag_by_cyl = None
        if engine.simulation_settings.enable_0d_to_1d_exhaust_coupling:
            if coupling_data is None:
                raise ValueError("0D->1D exhaust coupling enabled but no coupling data provided")
            p_stag_by_cyl = {}
            t_stag_by_cyl = {}
            base_angle = (solver.time * rpm * 6.0) % 720.0
            for cyl_id in range(1, solver.n_cyl + 1):
                data = coupling_data.get(cyl_id)
                if data is None:
                    raise ValueError(f"Missing coupling data for cylinder {cyl_id}")
                cyl_angle = (base_angle + solver.phase_map.get(cyl_id, 0.0)) % 720.0
                angle_arr = data["angle"]
                p_arr = data["p_stag"]
                t_arr = data["t_stag"]
                p_stag_by_cyl[cyl_id] = float(np.interp(cyl_angle, angle_arr, p_arr))
                t_stag_by_cyl[cyl_id] = float(np.interp(cyl_angle, angle_arr, t_arr))

        solver.step(rpm=rpm, dt=dt, p_stag_by_cyl=p_stag_by_cyl, T_stag_by_cyl=t_stag_by_cyl)
        times.append(float(solver.time))
        if source == "primary":
            U = solver.primary_states[0]["U"]
            p_grid = (solver.gamma - 1.0) * (
                U[:, 2] - 0.5 * (U[:, 1] ** 2) / np.maximum(U[:, 0], 1e-12)
            )
            pressures.append(float(p_grid[-1]))
        else:
            p_col, _T_col, _rho_col = solver.collector.get_state()
            pressures.append(float(p_col))
    if not times:
        raise RuntimeError("audio trace produced no samples")

    return times, pressures


def run_sweep(
    engine_path: Path,
    rpm: float,
    out_path: Path,
    runner_lengths: list[float] | None = None,
    points: int = 5,
    span_mm: float = 200.0,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    _run_preflight(engine, operation="sweep", mode="v1")
    lengths = runner_lengths or _runner_length_grid(
        base_mm=float(engine.intake.runner_length),
        points=points,
        span_mm=span_mm,
    )
    results = []
    for length in lengths:
        sweep_engine = Engine.from_dict(engine.to_dict())
        sweep_engine.intake.runner_length = float(length)
        sim = CylinderSimulator(sweep_engine)
        cycle = sim.run_cycle(float(rpm))
        results.append(
            {
                "runner_length_mm": float(length),
                "rpm": float(rpm),
                "mean_power_hp": float(cycle["mean_power_hp"]),
                "mean_torque_nm": float(cycle["mean_torque_nm"]),
                "bmep_bar": float(cycle["bmep_bar"]),
            }
        )

    output = {
        "metadata": _metadata(
            engine,
            raw,
            coupling_mode="none",
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        ),
        "sweep": {
            "param": "intake.runner_length",
            "unit": "mm",
            "rpm": float(rpm),
            "values": [float(v) for v in lengths],
        },
        "results": results,
    }
    _write_json(out_path, output)


def run_map(
    engine_path: Path,
    rpm_grid: list[float],
    throttle_grid: list[float],
    out_path: Path,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    if not rpm_grid:
        raise ValueError("rpm_grid must be non-empty")
    if not throttle_grid:
        raise ValueError("throttle_grid must be non-empty")
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    _run_preflight(engine, operation="map", mode="v1")
    points = run_partload_map(engine, rpm_grid, throttle_grid)
    output = {
        "metadata": _metadata(
            engine,
            raw,
            coupling_mode="map_runner",
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        ),
        "grid": {
            "rpm": [float(v) for v in rpm_grid],
            "throttle": [float(v) for v in throttle_grid],
        },
        "points": [p.to_dict() for p in points],
    }
    apply_observable_semantics(output, OBSERVABLE_VE_ACTUAL)
    _write_json(out_path, output)


def run_calibrate(
    engine_path: Path,
    target_path: Path,
    out_path: Path,
    params: list[str],
    max_evals: int,
    *,
    diagnostics: bool = False,
    multi_start: int = 1,
    eps_obj: float = 1e-3,
    eps_params: float = 0.05,
    top_k: int = 5,
    seed: int = 0,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )

    if diagnostics:
        target = json.loads(target_path.read_text(encoding="utf-8"))
        points = target.get("points") or target.get("targets") or []
        if not isinstance(points, list) or not points:
            raise ValueError("target file must include non-empty 'points' list")
        report = calibrate_engine_diagnostics(
            engine,
            points,
            params,
            max_evals,
            multi_start=multi_start,
            top_k=top_k,
            seed=seed,
            eps_obj=eps_obj,
            eps_params=eps_params,
        )
        output = {
            "metadata": {
                **_metadata(
                    engine,
                    raw,
                    coupling_mode="calibrate_diagnostics",
                    legacy_compat=legacy_profile,
                    legacy_overrides=legacy_overrides,
                ),
                **report["metadata"],
            },
            "best_solution": report["best_solution"],
            "top_k": report["top_k"],
            "uniqueness": report["uniqueness"],
            "evals_used": report["evals_used"],
            "status": report["status"],
        }
    else:
        report, calibrated_raw = run_reproducible_calibration(
            engine,
            raw,
            base_engine_path=engine_path,
            target_path=target_path,
            params=params,
            max_evals=max_evals,
        )
        calibrated_engine_path = out_path.with_name("calibrated_engine.json")
        calibrated_engine_path.parent.mkdir(parents=True, exist_ok=True)
        calibrated_engine_path.write_text(json.dumps(calibrated_raw, indent=2), encoding="utf-8")
        report["artifacts"]["calibrated_engine"] = str(calibrated_engine_path)
        output = {
            "metadata": _metadata(
                engine,
                raw,
                coupling_mode="calibrate",
                legacy_compat=legacy_profile,
                legacy_overrides=legacy_overrides,
            ),
            **report,
        }
    _write_json(out_path, output)


def run_calibrate_bmep(
    engine_path: Path,
    rpm: float,
    target_bmep_bar: float,
    out_path: Path,
    ca50_grid: list[float],
    duration_grid: list[float],
    *,
    wiebe_a: float | None = None,
    wiebe_m: float | None = None,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    report = calibrate_bmep(
        engine,
        rpm,
        target_bmep_bar,
        ca50_grid,
        duration_grid,
        wiebe_a=wiebe_a,
        wiebe_m=wiebe_m,
        require_no_knock=True,
    )
    output = {
        "metadata": _metadata(
            engine,
            raw,
            coupling_mode="calibrate_bmep",
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        ),
        **report.to_dict(),
    }
    _write_json(out_path, output)


def run_optimize(
    engine_path: Path,
    target_path: Path,
    out_path: Path,
    param: str,
    bounds_m: tuple[float, float],
    seed: int,
    max_evals: int,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    points = load_target_points(str(target_path))
    report = optimize_runner_length(
        engine,
        points,
        bounds_m=bounds_m,
        seed=seed,
        max_evals=max_evals,
        param=param,
    )
    output = {
        "metadata": _metadata(
            engine,
            raw,
            coupling_mode="optimize",
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        ),
        **report.to_dict(),
    }
    _write_json(out_path, output)


def run_optimize_guided(
    engine_path: Path,
    out_path: Path,
    *,
    objective: str,
    params: list[str],
    seed: int,
    max_evals: int,
    target_path: Path | None = None,
    rpm_grid: list[float] | None = None,
    bounds_map: dict[str, tuple[float, float]] | None = None,
    max_signal_mape: dict[str, float] | None = None,
    min_peak_power_hp: float | None = None,
    min_mean_torque_nm: float | None = None,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    target_points = load_target_points(str(target_path)) if target_path is not None else None
    constraints: dict[str, object] = {}
    if max_signal_mape:
        constraints["max_signal_mape"] = dict(max_signal_mape)
    if min_peak_power_hp is not None:
        constraints["min_peak_power_hp"] = float(min_peak_power_hp)
    if min_mean_torque_nm is not None:
        constraints["min_mean_torque_nm"] = float(min_mean_torque_nm)
    report = optimize_guided(
        engine,
        objective=objective,
        params=params,
        seed=seed,
        max_evals=max_evals,
        target_points=target_points,
        rpm_grid=rpm_grid,
        param_bounds=bounds_map or {},
        constraints=constraints,
    )
    output = {
        "metadata": _metadata(
            engine,
            raw,
            coupling_mode="optimize_guided",
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        ),
        **report.to_dict(),
    }
    optimize_context = build_report_context(engine_path=engine_path)
    if target_path is not None and target_path.is_dir():
        optimize_context = build_report_context(
            **optimize_context,
            **dataset_context_from_dir(target_path),
        )
    apply_analysis_envelope(
        output,
        report_type=REPORT_TYPE_OPTIMIZE_GUIDED,
        context=optimize_context,
        generated_at_utc=str(output.get("metadata", {}).get("timestamp", "")) or None,
    )
    _write_json(out_path, output)


def run_full_scope(
    engine_path: Path,
    duration: float,
    out_path: Path,
    *,
    max_steps: int | None = None,
    target_dx: float | None = None,
    use_numba: bool = False,
    time_budget_ms: float | None = None,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    _run_preflight(engine, operation="full_scope", mode="v2")
    result = run_full_scope_sim(
        engine,
        duration_s=float(duration),
        max_steps=max_steps,
        target_dx=target_dx,
        use_numba=use_numba,
        time_budget_ms=time_budget_ms,
    )
    output = {
        "metadata": _metadata(
            engine,
            raw,
            coupling_mode="full_network",
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        ),
        "duration_s": float(duration),
        "dt_min": float(result.dt_min),
        "dt_max": float(result.dt_max),
        "steps_used": int(result.steps_used),
        "status": result.status,
        "per_cyl": result.per_cyl,
        "traces": {
            "time": result.time_s,
            "intake_plenum_pa": result.intake_plenum_pa,
            "exhaust_plenum_pa": result.exhaust_plenum_pa,
            "runner_stats": result.runner_stats,
        },
    }
    apply_observable_semantics(output, OBSERVABLE_VE_ACTUAL)
    _write_json(out_path, output)


def run_benchmark(
    engine_path: Path,
    dataset_dir: Path,
    out_path: Path,
    *,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
    adaptive_combustion: str = "as_is",
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    engine, raw, combustion_summary = apply_adaptive_combustion_mode(
        engine,
        raw,
        mode=adaptive_combustion,
    )
    report = evaluate_with_engine(engine, raw, dataset_dir)
    report.metadata["version"] = _git_version()
    if legacy_profile:
        report.metadata["legacy_compat"] = legacy_profile
    if legacy_overrides:
        report.metadata["legacy_overrides"] = legacy_overrides
    report.metadata["combustion"] = combustion_summary
    output = report.to_dict()
    apply_analysis_envelope(
        output,
        report_type=REPORT_TYPE_COMPARE,
        context=build_report_context(engine_path=engine_path),
        generated_at_utc=str(output.get("metadata", {}).get("timestamp", "")) or None,
    )
    _write_json(out_path, output)


def run_bench_import(
    csv_path: Path,
    out_path: Path,
    *,
    dataset_id: str,
    engine_id: str,
    preset_path: str,
    torque_units: str,
    power_units: str,
    notes: str,
    torque_mape_max: float,
    power_mape_max: float,
    ) -> None:
    write_dataset_package(
        csv_path,
        out_path,
        dataset_id=dataset_id,
        engine_id=engine_id,
        preset_path=preset_path,
        torque_units=torque_units,
        power_units=power_units,
        notes=notes,
        error_contract={
            "torque_mape_max": float(torque_mape_max),
            "power_mape_max": float(power_mape_max),
        },
    )


def run_dyno_import(
    input_path: Path,
    out_path: Path,
    *,
    dataset_id: str,
    engine_id: str,
    preset_path: str,
    source_format: str,
    mapping: str,
    units: str,
    notes: str,
    torque_mape_max: float,
    power_mape_max: float,
    afr_stoich: float,
) -> None:
    write_flexible_dataset_package(
        input_path,
        out_path,
        dataset_id=dataset_id,
        engine_id=engine_id,
        preset_path=preset_path,
        notes=notes,
        error_contract={
            "torque_mape_max": float(torque_mape_max),
            "power_mape_max": float(power_mape_max),
        },
        source_format=source_format,
        mapping=parse_mapping_text(mapping),
        units=parse_units_text(units),
        afr_stoich=float(afr_stoich),
    )


def run_dyno_compare(
    engine_path: Path,
    dataset_dir: Path,
    out_path: Path,
    *,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
    adaptive_combustion: str = "as_is",
) -> None:
    run_benchmark(
        engine_path,
        dataset_dir,
        out_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
        adaptive_combustion=adaptive_combustion,
    )


def run_calibrate_staged(
    engine_path: Path,
    dataset_dir: Path,
    out_path: Path,
    *,
    max_evals_per_stage: int,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
    adaptive_combustion: str = "as_is",
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    engine, raw, combustion_summary = apply_adaptive_combustion_mode(
        engine,
        raw,
        mode=adaptive_combustion,
    )
    report, calibrated_raw, bench_before, bench_after = run_staged_calibration(
        engine,
        raw,
        base_engine_path=engine_path,
        dataset_dir=dataset_dir,
        max_evals_per_stage=max_evals_per_stage,
    )
    calibrated_engine_path = out_path.with_name("calibrated_engine.json")
    benchmark_before_path = out_path.with_name("benchmark_before.json")
    benchmark_after_path = out_path.with_name("benchmark_after.json")
    calibrated_engine_path.parent.mkdir(parents=True, exist_ok=True)
    calibrated_engine_path.write_text(json.dumps(calibrated_raw, indent=2), encoding="utf-8")
    benchmark_before_path.write_text(json.dumps(bench_before, indent=2), encoding="utf-8")
    benchmark_after_path.write_text(json.dumps(bench_after, indent=2), encoding="utf-8")
    report["artifacts"]["calibrated_engine"] = str(calibrated_engine_path)
    report["artifacts"]["benchmark_before"] = str(benchmark_before_path)
    report["artifacts"]["benchmark_after"] = str(benchmark_after_path)
    output = {
        "metadata": _metadata(
            Engine.from_dict(calibrated_raw),
            raw,
            coupling_mode="staged_calibration",
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        ),
        **report,
    }
    output["metadata"]["combustion"] = combustion_summary
    output["combustion_requested"] = combustion_summary
    apply_analysis_envelope(
        output,
        report_type=REPORT_TYPE_STAGED_CALIBRATION,
        generated_at_utc=str(output.get("metadata", {}).get("timestamp", "")) or None,
    )
    _write_json(out_path, output)


def _cutlist_text_path(out_path: Path) -> Path:
    if out_path.suffix:
        return out_path.with_suffix(".txt")
    return out_path.with_name(out_path.name + ".txt")


def run_cutlist(
    engine_path: Path,
    out_path: Path,
    *,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    block = engine.block
    intake = engine.intake
    exhaust = engine.exhaust

    cut_items = [
        {
            "name": "intake_runner",
            "count": int(block.num_cylinders),
            "length_mm": float(intake.runner_length),
            "diameter_mm": float(intake.runner_diameter),
        },
        {
            "name": "exhaust_primary",
            "count": int(block.num_cylinders),
            "length_mm": float(exhaust.header_primary_length),
            "diameter_mm": float(exhaust.header_primary_diameter),
        },
        {
            "name": "exhaust_collector",
            "count": 1,
            "length_mm": float(exhaust.collector_length),
        },
    ]

    output = {
        "metadata": _metadata(
            engine,
            raw,
            coupling_mode="none",
            legacy_compat=legacy_profile,
            legacy_overrides=legacy_overrides,
        ),
        "engine": {
            "model_name": engine.model_name,
            "num_cylinders": int(block.num_cylinders),
            "firing_order": list(block.firing_order),
        },
        "intake": {
            "runner_length_mm": float(intake.runner_length),
            "runner_diameter_mm": float(intake.runner_diameter),
            "plenum_volume_l": float(intake.plenum_volume),
            "throttle_body_dia_mm": float(intake.throttle_body_dia),
        },
        "exhaust": {
            "primary_length_mm": float(exhaust.header_primary_length),
            "primary_diameter_mm": float(exhaust.header_primary_diameter),
            "collector_length_mm": float(exhaust.collector_length),
        },
        "cutlist": cut_items,
    }
    _write_json(out_path, output)

    text_lines = [
        f"model_name: {engine.model_name}",
        f"num_cylinders: {int(block.num_cylinders)}",
        f"intake.runner_length_mm: {float(intake.runner_length):.2f}",
        f"intake.runner_diameter_mm: {float(intake.runner_diameter):.2f}",
        f"exhaust.primary_length_mm: {float(exhaust.header_primary_length):.2f}",
        f"exhaust.primary_diameter_mm: {float(exhaust.header_primary_diameter):.2f}",
        f"exhaust.collector_length_mm: {float(exhaust.collector_length):.2f}",
    ]
    text_path = _cutlist_text_path(out_path)
    text_path.write_text("\n".join(text_lines) + "\n", encoding="utf-8")


def run_validate_features(
    engine_path: Path,
    dataset_dirs: list[Path],
    out_path: Path,
    *,
    include_adaptive_toggle: bool,
    include_turbo_toggle: bool,
    include_staged_calibration: bool,
    max_evals_per_stage: int,
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    payload = run_validation_batch(
        engine,
        raw,
        base_engine_path=engine_path,
        dataset_dirs=dataset_dirs,
        include_adaptive_toggle=include_adaptive_toggle,
        include_turbo_toggle=include_turbo_toggle,
        include_staged_calibration=include_staged_calibration,
        max_evals_per_stage=max_evals_per_stage,
    )
    payload["metadata"]["version"] = _git_version()
    if legacy_profile:
        payload["metadata"]["legacy_compat"] = legacy_profile
    if legacy_overrides:
        payload["metadata"]["legacy_overrides"] = legacy_overrides
    _write_json(out_path, payload)


def run_compare_ab(
    engine_a_path: Path,
    engine_b_path: Path,
    dataset_dir: Path,
    out_path: Path,
    *,
    label_a: str,
    label_b: str,
    adaptive_combustion_a: str = "as_is",
    adaptive_combustion_b: str = "as_is",
    turbo_incremental_a: str = "as_is",
    turbo_incremental_b: str = "as_is",
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine_a, raw_a, legacy_profile_a, legacy_overrides_a = _load_engine_with_legacy(
        engine_a_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    engine_b, raw_b, legacy_profile_b, legacy_overrides_b = _load_engine_with_legacy(
        engine_b_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    engine_a, raw_a, combustion_a = apply_adaptive_combustion_mode(engine_a, raw_a, mode=adaptive_combustion_a)
    engine_b, raw_b, combustion_b = apply_adaptive_combustion_mode(engine_b, raw_b, mode=adaptive_combustion_b)
    engine_a, raw_a, turbo_a = apply_turbo_incremental_mode(engine_a, raw_a, mode=turbo_incremental_a)
    engine_b, raw_b, turbo_b = apply_turbo_incremental_mode(engine_b, raw_b, mode=turbo_incremental_b)
    payload = run_ab_compare(
        engine_a,
        raw_a,
        engine_b,
        raw_b,
        dataset_dir=dataset_dir,
        label_a=label_a,
        label_b=label_b,
    )
    payload["metadata"] = {
        "version": _git_version(),
        "engine_a_path": str(engine_a_path),
        "engine_b_path": str(engine_b_path),
        "legacy_compat_a": legacy_profile_a,
        "legacy_compat_b": legacy_profile_b,
        "legacy_overrides_a": legacy_overrides_a,
        "legacy_overrides_b": legacy_overrides_b,
        "config_a": {
            "combustion": combustion_a,
            "turbo_incremental": turbo_a,
        },
        "config_b": {
            "combustion": combustion_b,
            "turbo_incremental": turbo_b,
        },
    }
    _write_json(out_path, payload)


def run_sensitivity_local(
    engine_path: Path,
    dataset_dir: Path,
    out_path: Path,
    *,
    params: list[str],
    adaptive_combustion: str = "as_is",
    turbo_incremental: str = "as_is",
    legacy_compat: str | None = None,
    auto_legacy_compat: bool = False,
) -> None:
    engine, raw, legacy_profile, legacy_overrides = _load_engine_with_legacy(
        engine_path,
        legacy_compat=legacy_compat,
        auto_legacy_compat=auto_legacy_compat,
    )
    engine, raw, combustion_summary = apply_adaptive_combustion_mode(engine, raw, mode=adaptive_combustion)
    engine, raw, turbo_summary = apply_turbo_incremental_mode(engine, raw, mode=turbo_incremental)
    payload = run_local_sensitivity(
        engine,
        raw,
        dataset_dir=dataset_dir,
        params=params,
    )
    payload["metadata"] = {
        "version": _git_version(),
        "engine_path": str(engine_path),
        "params_requested": params,
        "legacy_compat": legacy_profile,
        "legacy_overrides": legacy_overrides,
        "config": {
            "combustion": combustion_summary,
            "turbo_incremental": turbo_summary,
        },
    }
    apply_analysis_envelope(
        payload,
        report_type=REPORT_TYPE_SENSITIVITY_LOCAL,
        context=build_report_context(engine_path=engine_path),
    )
    _write_json(out_path, payload)


def _read_expectations(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _case_engine_path(expectations_path: Path, case_file: str) -> Path:
    base = expectations_path.parent
    return (base / case_file).resolve()


def _check_finite(name: str, array: np.ndarray, issues: list[str]) -> None:
    if not np.isfinite(array).all():
        issues.append(f"{name} contains NaN/inf")


def _monotonic_non_decreasing(values: Sequence[float]) -> bool:
    if len(values) < 2:
        return True
    return all(values[idx] >= values[idx - 1] - 1e-9 for idx in range(1, len(values)))


def _metric_from_cycle(metric: str, cycle: dict) -> float:
    if metric == "mean_torque_nm":
        return float(cycle.get("mean_torque_nm", 0.0))
    if metric == "mean_power_hp":
        return float(cycle.get("mean_power_hp", 0.0))
    if metric == "mean_temperature_k":
        temps = np.asarray(cycle.get("temperature", []), dtype=float)
        if temps.size == 0:
            return float("nan")
        return float(np.mean(temps))
    raise ValueError(f"Unknown metric '{metric}'")


def _metric_from_full_scope(metric: str, result) -> float:
    if metric == "intake_plenum_std":
        values = np.asarray(result.intake_plenum_pa, dtype=float)
        if values.size == 0:
            return float("nan")
        return float(np.std(values))
    raise ValueError(f"Unknown full_scope metric '{metric}'")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _cycle_physical_invariants(engine: Engine, rpm: float, cycle: dict) -> dict:
    torque_nm = float(cycle["mean_torque_nm"])
    power_hp = float(cycle["mean_power_hp"])
    bmep_bar = float(cycle["bmep_bar"])
    ve_actual = float(cycle["ve_actual"])
    omega = float(rpm) * 2.0 * math.pi / 60.0
    expected_power_hp = torque_nm * omega / 745.7
    displacement_m3 = max(cc_to_m3(engine.block.displacement_cc), 1e-12)
    expected_bmep_bar = torque_nm * 4.0 * math.pi / displacement_m3 / 100000.0
    power_rel_error = abs(power_hp - expected_power_hp) / max(abs(expected_power_hp), 1e-9)
    bmep_rel_error = abs(bmep_bar - expected_bmep_bar) / max(abs(expected_bmep_bar), 1e-9)
    return {
        "power_from_torque_consistent": bool(power_rel_error <= 1e-6),
        "bmep_from_torque_consistent": bool(bmep_rel_error <= 1e-6),
        "positive_absolute_pressure": bool(float(np.min(cycle["pressure"])) > 0.0),
        "positive_absolute_temperature": bool(float(np.min(cycle["temperature"])) > 0.0),
        "ve_actual_in_bounds": bool(0.0 <= ve_actual <= 1.5),
        "power_rel_error": float(power_rel_error),
        "bmep_rel_error": float(bmep_rel_error),
    }


def run_selfcheck(expectations_path: Path, out_path: Path) -> int:
    expectations = _read_expectations(expectations_path)
    cases = expectations.get("cases", [])
    report: dict = {"cases": [], "status": "pass"}
    exit_code = 0

    for case in cases:
        case_name = case.get("file")
        if not case_name:
            continue
        engine_path = _case_engine_path(expectations_path, case_name)
        issues: list[str] = []
        case_entry = {"file": case_name, "issues": issues, "checks": {}}
        try:
            engine, raw, _legacy_profile, _legacy_overrides = _load_engine_with_legacy(engine_path)
            simulator = CylinderSimulator(engine)

            dyno_rpms: Sequence[float] = case.get("rpm", [])
            dyno_results = []
            for rpm in dyno_rpms:
                cycle = simulator.run_cycle(float(rpm))
                dyno_results.append(cycle)
                _check_finite("pressure", cycle["pressure"], issues)
                _check_finite("temperature", cycle["temperature"], issues)
                if np.min(cycle["pressure"]) <= 0:
                    issues.append("pressure <= 0")
                if np.min(cycle["temperature"]) <= 0:
                    issues.append("temperature <= 0")
                ve_val = float(cycle.get("ve_actual", 0.0))
                if not (0.0 <= ve_val <= 1.5):
                    issues.append("ve out of bounds")
            if dyno_results:
                invariants = []
                for rpm, cycle in zip(dyno_rpms, dyno_results):
                    entry = {"rpm": float(rpm), **_cycle_physical_invariants(engine, float(rpm), cycle)}
                    invariants.append(entry)
                    if not entry["power_from_torque_consistent"]:
                        issues.append(f"power/torque invariant failed at rpm={float(rpm):.1f}")
                    if not entry["bmep_from_torque_consistent"]:
                        issues.append(f"bmep/torque invariant failed at rpm={float(rpm):.1f}")
                    if not entry["positive_absolute_pressure"]:
                        issues.append(f"pressure invariant failed at rpm={float(rpm):.1f}")
                    if not entry["positive_absolute_temperature"]:
                        issues.append(f"temperature invariant failed at rpm={float(rpm):.1f}")
                    if not entry["ve_actual_in_bounds"]:
                        issues.append(f"ve invariant failed at rpm={float(rpm):.1f}")
                case_entry["checks"]["physical_invariants"] = invariants

            power_min = case.get("power_hp_min", [])
            power_max = case.get("power_hp_max", [])
            if power_min and power_max and len(dyno_results) == len(power_min):
                for idx, cycle in enumerate(dyno_results):
                    power = float(cycle["mean_power_hp"])
                    if power < power_min[idx] or power > power_max[idx]:
                        issues.append(f"power_hp out of range at idx={idx}")

            throttle_grid = case.get("throttle_grid", [])
            throttle_metric = case.get("throttle_metric")
            throttle_rpm = case.get("throttle_rpm")
            if throttle_grid and throttle_metric and throttle_rpm is not None:
                map_points = run_partload_map(engine, [float(throttle_rpm)], throttle_grid)
                values = [_metric_from_cycle(throttle_metric, {"mean_torque_nm": p.torque_nm, "mean_power_hp": p.power_hp})
                          for p in map_points]
                case_entry["checks"]["throttle_grid"] = {
                    "rpm": float(throttle_rpm),
                    "values": [float(v) for v in values],
                }
                if not _monotonic_non_decreasing(values):
                    issues.append("throttle_metric not monotonic with throttle")

            compare_to = case.get("compare_to")
            if compare_to:
                base_path = _case_engine_path(expectations_path, compare_to.get("file", ""))
                metric = compare_to.get("metric")
                relation = compare_to.get("relation")
                mode = compare_to.get("mode", "dyno")
                rpm = float(compare_to.get("rpm", 0.0))
                if rpm <= 0.0:
                    rpm_list = case.get("rpm", [])
                    rpm = float(rpm_list[0]) if rpm_list else 0.0
                if not metric or not relation:
                    issues.append("compare_to missing metric or relation")
                else:
                    if mode == "full_scope":
                        full_scope_cfg = case.get("full_scope", {})
                        duration_s = float(full_scope_cfg.get("duration_s", compare_to.get("duration_s", 0.01)))
                        max_steps = full_scope_cfg.get("max_steps", compare_to.get("max_steps"))
                        target_dx = full_scope_cfg.get("target_dx", compare_to.get("target_dx"))
                        base_engine, _, _base_profile, _base_overrides = _load_engine_with_legacy(base_path)
                        base_result = run_full_scope_sim(
                            base_engine,
                            duration_s=duration_s,
                            max_steps=max_steps,
                            target_dx=target_dx,
                            rpm=rpm if rpm > 0 else None,
                        )
                        base_value = _metric_from_full_scope(metric, base_result)
                        result = run_full_scope_sim(
                            engine,
                            duration_s=duration_s,
                            max_steps=max_steps,
                            target_dx=target_dx,
                            rpm=rpm if rpm > 0 else None,
                        )
                        value = _metric_from_full_scope(metric, result)
                    else:
                        if rpm <= 0.0:
                            issues.append("compare_to rpm missing")
                            base_value = float("nan")
                            value = float("nan")
                        else:
                            base_engine, _, _base_profile, _base_overrides = _load_engine_with_legacy(base_path)
                            base_cycle = CylinderSimulator(base_engine).run_cycle(rpm)
                            base_value = _metric_from_cycle(metric, base_cycle)
                            value = _metric_from_cycle(metric, simulator.run_cycle(rpm))

                    case_entry["checks"]["compare_to"] = {
                        "metric": metric,
                        "value": float(value),
                        "baseline": float(base_value),
                        "relation": relation,
                        "mode": mode,
                    }
                    if np.isfinite(value) and np.isfinite(base_value):
                        if relation == "less" and not value < base_value:
                            issues.append("compare_to metric not less than baseline")
                        if relation == "greater" and not value > base_value:
                            issues.append("compare_to metric not greater than baseline")

            scope_cfg = case.get("scope")
            if scope_cfg:
                rpm = float(scope_cfg.get("rpm", 2000.0))
                cycles = int(scope_cfg.get("cycles", 1))
                max_steps = scope_cfg.get("max_steps")
                time_budget_ms = scope_cfg.get("time_budget_ms")
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
                solver = _build_wave_solver(engine)
                history, _, _ = solver.run_full_simulation(
                    rpm,
                    cycles=cycles,
                    coupling_data=coupling_data,
                    max_steps=max_steps,
                    time_budget_ms=time_budget_ms,
                )
                matrix = compute_pressure_matrix(history, solver.gamma)
                _check_finite("scope_pressure", matrix, issues)
                min_span = float(scope_cfg.get("min_span", 0.0))
                if matrix.size > 0 and float(matrix.max() - matrix.min()) < min_span:
                    issues.append("scope pressure span too small")

                case_entry["checks"]["coupling_mode"] = coupling_mode

            metadata = _metadata(engine, raw, coupling_mode=case_entry["checks"].get("coupling_mode", "none"))
            if not all(key in metadata for key in ("input_hash", "settings", "coupling_mode")):
                issues.append("metadata missing required keys")

            case_entry["metadata"] = metadata
        except Exception as exc:
            report["status"] = "error"
            case_entry["issues"].append(str(exc))
            exit_code = 3
        else:
            if issues:
                report["status"] = "issues"
                if exit_code == 0:
                    exit_code = 2

        report["cases"].append(case_entry)

    _write_json(out_path, report)
    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pywavedyn.cli", description="PyWaveDyn headless CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    dyno = sub.add_parser("dyno", help="Run a 0D dyno sweep")
    dyno.add_argument("--engine", required=True, type=Path)
    dyno.add_argument("--rpm", required=True, help="RPM or range start:end:step")
    dyno.add_argument("--mode", choices=["v1", "v2"], default="v1")
    dyno.add_argument("--turbo", type=Path, default=None)
    dyno.add_argument("--settle-cycles", type=int, default=0, help="Extra cycles to settle v2 before first point")
    dyno.add_argument(
        "--min-periodicity",
        type=float,
        default=None,
        help="Mark v2 points as not converged when periodicity error exceeds this",
    )
    dyno.add_argument(
        "--drop-invalid",
        action="store_true",
        help="Drop v2 points marked not converged (opt-in)",
    )
    dyno.add_argument(
        "--rpm-start-safe",
        action="store_true",
        help="Warm-start v2 at a safe RPM before the sweep",
    )
    dyno.add_argument(
        "--debug-dyno-v2",
        action="store_true",
        help="Log v2 VE numerator/denominator at 7000 rpm (debug)",
    )
    dyno.add_argument(
        "--knock-report",
        type=Path,
        default=None,
        help="Write knock report JSON (opt-in; requires residual coupling).",
    )
    _add_legacy_args(dyno)
    _add_adaptive_combustion_arg(dyno)
    dyno.add_argument("--out", required=True, type=Path)

    scope = sub.add_parser("scope", help="Run a 1D wave scope")
    scope.add_argument("--engine", required=True, type=Path)
    scope.add_argument("--rpm", required=True, type=float)
    scope.add_argument("--cycles", type=int, default=2)
    scope.add_argument("--target-dx", type=float, default=None)
    scope.add_argument("--max-steps", type=int, default=None)
    _add_legacy_args(scope)
    scope.add_argument("--out", required=True, type=Path)

    intake_scope = sub.add_parser("intake-scope", help="Run a headless intake 1D scope")
    intake_scope.add_argument("--engine", required=True, type=Path)
    intake_scope.add_argument("--target-dx", type=float, default=None)
    intake_scope.add_argument("--max-steps", type=int, default=None)
    _add_legacy_args(intake_scope)
    intake_scope.add_argument("--out", required=True, type=Path)

    bench_import = sub.add_parser("bench-import", help="Import canonical real-data CSV into benchmark dataset package")
    bench_import.add_argument("--csv", required=True, type=Path)
    bench_import.add_argument("--out", required=True, type=Path, help="Output dataset directory")
    bench_import.add_argument("--dataset-id", required=True)
    bench_import.add_argument("--engine-id", required=True)
    bench_import.add_argument("--preset-path", required=True)
    bench_import.add_argument("--torque-units", choices=["lbft", "nm"], default="lbft")
    bench_import.add_argument("--power-units", choices=["hp", "kw"], default="hp")
    bench_import.add_argument("--notes", default="")
    bench_import.add_argument("--torque-mape-max", type=float, default=1.0)
    bench_import.add_argument("--power-mape-max", type=float, default=1.0)

    dyno_import = sub.add_parser("dyno-import", help="Import flexible dyno CSV/JSON into canonical dataset package")
    dyno_import.add_argument("--input", required=True, type=Path)
    dyno_import.add_argument("--out", required=True, type=Path, help="Output dataset directory")
    dyno_import.add_argument("--dataset-id", required=True)
    dyno_import.add_argument("--engine-id", required=True)
    dyno_import.add_argument("--preset-path", required=True)
    dyno_import.add_argument("--format", choices=["auto", "csv", "json"], default="auto")
    dyno_import.add_argument(
        "--mapping",
        required=True,
        help="Comma list of canonical=source_field. Canonical signals: rpm, torque_nm, power_hp, boost_kpa, map_kpa, lambda, afr, egt_c",
    )
    dyno_import.add_argument(
        "--units",
        required=True,
        help="Comma list of canonical=unit. Example: torque_nm=lbft,power_hp=hp,boost_kpa=psi_g,map_kpa=kpa_abs,egt_c=f",
    )
    dyno_import.add_argument("--afr-stoich", type=float, default=14.7)
    dyno_import.add_argument("--notes", default="")
    dyno_import.add_argument("--torque-mape-max", type=float, default=1.0)
    dyno_import.add_argument("--power-mape-max", type=float, default=1.0)

    audio = sub.add_parser("audio", help="Render multi-cylinder audio WAV (headless)")
    audio.add_argument("--engine", required=True, type=Path)
    audio.add_argument("--rpm", required=True, type=float)
    audio.add_argument("--duration", type=float, default=2.0)
    audio.add_argument("--sample-rate", type=int, default=44_100)
    audio.add_argument("--firing-order", type=str, default="")
    audio.add_argument(
        "--source",
        choices=["runner", "primary", "exhaust_plenum"],
        default="runner",
        help="Audio source (default matches existing synthetic runner output).",
    )
    _add_legacy_args(audio)
    audio.add_argument("--out", required=True, type=Path)

    sweep = sub.add_parser("sweep", help="Run a headless sweep (runner length)")
    sweep.add_argument("--engine", required=True, type=Path)
    sweep.add_argument("--rpm", required=True, type=float)
    sweep.add_argument("--runner-lengths", type=str, default="")
    sweep.add_argument("--points", type=int, default=5)
    sweep.add_argument("--span-mm", type=float, default=200.0)
    _add_legacy_args(sweep)
    sweep.add_argument("--out", required=True, type=Path)

    map_cmd = sub.add_parser("map", help="Run a headless part-load map")
    map_cmd.add_argument("--engine", required=True, type=Path)
    map_cmd.add_argument("--rpm-grid", required=True, type=str)
    map_cmd.add_argument("--throttle-grid", required=True, type=str)
    _add_legacy_args(map_cmd)
    map_cmd.add_argument("--out", required=True, type=Path)

    calibrate = sub.add_parser("calibrate", help="Run bounded auto-calibration against target curve")
    calibrate.add_argument("--engine", required=True, type=Path)
    calibrate.add_argument("--target", required=True, type=Path)
    calibrate.add_argument("--out", required=True, type=Path)
    calibrate.add_argument("--max-evals", type=int, default=40)
    calibrate.add_argument("--params", type=str, default="ve_scale,friction_scale,burn_scale")
    calibrate.add_argument("--diagnostics", action="store_true", help="Enable diagnostics/uniqueness report")
    calibrate.add_argument("--multi-start", type=int, default=1, help="Number of multi-start seeds")
    calibrate.add_argument("--eps-obj", type=float, default=1e-3, help="Objective tolerance for non-uniqueness")
    calibrate.add_argument("--eps-params", type=float, default=0.05, help="Param spread tolerance for non-uniqueness")
    calibrate.add_argument("--top-k", type=int, default=5, help="Number of top solutions to retain")
    calibrate.add_argument("--seed", type=int, default=0, help="Seed for diagnostics sampling")
    _add_legacy_args(calibrate)

    calibrate_bmep = sub.add_parser("calibrate-bmep", help="Calibrate Wiebe timing to target BMEP (opt-in)")
    calibrate_bmep.add_argument("--engine", required=True, type=Path)
    calibrate_bmep.add_argument("--rpm", required=True, type=float)
    calibrate_bmep.add_argument("--target-bmep", required=True, type=float)
    calibrate_bmep.add_argument("--ca50-range", type=str, default="6:12:1")
    calibrate_bmep.add_argument("--duration-range", type=str, default="14:26:2")
    calibrate_bmep.add_argument("--wiebe-a", type=float, default=None)
    calibrate_bmep.add_argument("--wiebe-m", type=float, default=None)
    _add_legacy_args(calibrate_bmep)
    calibrate_bmep.add_argument("--out", required=True, type=Path)

    optimize = sub.add_parser("optimize", help="Optimize runner length against target curve")
    optimize.add_argument("--engine", required=True, type=Path)
    optimize.add_argument("--target", required=True, type=Path)
    optimize.add_argument("--param", required=True, type=str)
    optimize.add_argument("--bounds", required=True, type=str, help="Bounds in meters: low,high")
    optimize.add_argument("--seed", type=int, default=123)
    optimize.add_argument("--max-evals", type=int, default=30)
    _add_legacy_args(optimize)
    optimize.add_argument("--out", required=True, type=Path)

    optimize_guided = sub.add_parser("optimize-guided", help="Run a guided local optimization on a small, interpretable parameter set")
    optimize_guided.add_argument("--engine", required=True, type=Path)
    optimize_guided.add_argument("--objective", choices=["dataset_error", "peak_power", "mean_torque_band", "boost_target_tracking"], required=True)
    optimize_guided.add_argument("--params", required=True, type=str, help="Comma-separated params. Up to 2 supported in this iteration.")
    optimize_guided.add_argument("--target", type=Path, default=None, help="Target JSON or canonical dataset directory for dataset_error objective")
    optimize_guided.add_argument("--rpm-grid", type=str, default="", help="RPM list for dyno-style objectives")
    optimize_guided.add_argument("--param-bounds", type=str, default="", help="Comma list param=low:high")
    optimize_guided.add_argument("--max-signal-mape", type=str, default="", help="Comma list signal=max_mape guardrail")
    optimize_guided.add_argument("--min-peak-power-hp", type=float, default=None)
    optimize_guided.add_argument("--min-mean-torque-nm", type=float, default=None)
    optimize_guided.add_argument("--seed", type=int, default=123)
    optimize_guided.add_argument("--max-evals", type=int, default=30)
    _add_legacy_args(optimize_guided)
    optimize_guided.add_argument("--out", required=True, type=Path)

    full_scope = sub.add_parser("full-scope", help="Run full intake+exhaust network scope")
    full_scope.add_argument("--engine", required=True, type=Path)
    full_scope.add_argument("--duration", required=True, type=float)
    full_scope.add_argument("--out", required=True, type=Path)
    full_scope.add_argument("--max-steps", type=int, default=None)
    full_scope.add_argument("--target-dx", type=float, default=None)
    full_scope.add_argument("--fast-numba", action="store_true", help="Enable Numba fast path (if available)")
    full_scope.add_argument("--time-budget-ms", type=float, default=None)
    _add_legacy_args(full_scope)

    cutlist = sub.add_parser("cutlist", help="Generate cut-list report (JSON + text)")
    cutlist_group = cutlist.add_mutually_exclusive_group(required=True)
    cutlist_group.add_argument("--engine", type=Path)
    cutlist_group.add_argument("--preset", type=Path, help=argparse.SUPPRESS)
    _add_legacy_args(cutlist)
    cutlist.add_argument("--out", required=True, type=Path)

    selfcheck = sub.add_parser("selfcheck", help="Run deterministic validation cases")
    selfcheck.add_argument(
        "--expectations",
        type=Path,
        default=Path("validation_cases/expectations.json"),
        help="Path to expectations.json",
    )
    selfcheck.add_argument("--out", type=Path, default=Path("selfcheck_report.json"))

    benchmark = sub.add_parser("benchmark", help="Run benchmark evaluation against dataset")
    benchmark.add_argument("--engine", required=True, type=Path)
    benchmark.add_argument("--dataset", required=True, type=Path)
    _add_legacy_args(benchmark)
    _add_adaptive_combustion_arg(benchmark)
    benchmark.add_argument("--out", required=True, type=Path)

    dyno_compare = sub.add_parser("dyno-compare", help="Compare simulator against canonical dyno dataset")
    dyno_compare.add_argument("--engine", required=True, type=Path)
    dyno_compare.add_argument("--dataset", required=True, type=Path)
    _add_legacy_args(dyno_compare)
    _add_adaptive_combustion_arg(dyno_compare)
    dyno_compare.add_argument("--out", required=True, type=Path)

    calibrate_staged = sub.add_parser("calibrate-staged", help="Run staged assisted calibration against dyno dataset")
    calibrate_staged.add_argument("--engine", required=True, type=Path)
    calibrate_staged.add_argument("--dataset", required=True, type=Path)
    calibrate_staged.add_argument("--out", required=True, type=Path)
    calibrate_staged.add_argument("--max-evals-per-stage", type=int, default=10)
    _add_legacy_args(calibrate_staged)
    _add_adaptive_combustion_arg(calibrate_staged)

    validate_features = sub.add_parser("validate-features", help="Run comparative validation across datasets and feature toggles")
    validate_features.add_argument("--engine", required=True, type=Path)
    validate_features.add_argument("--datasets", required=True, nargs="+", type=Path)
    validate_features.add_argument("--out", required=True, type=Path)
    validate_features.add_argument("--with-adaptive-toggle", action="store_true")
    validate_features.add_argument("--with-turbo-toggle", action="store_true")
    validate_features.add_argument("--with-staged-calibration", action="store_true")
    validate_features.add_argument("--max-evals-per-stage", type=int, default=10)
    _add_legacy_args(validate_features)

    compare_ab = sub.add_parser("compare-ab", help="Compare two engine configurations A/B on the same dataset")
    compare_ab.add_argument("--engine-a", required=True, type=Path)
    compare_ab.add_argument("--engine-b", required=True, type=Path)
    compare_ab.add_argument("--dataset", required=True, type=Path)
    compare_ab.add_argument("--label-a", default="A")
    compare_ab.add_argument("--label-b", default="B")
    _add_legacy_args(compare_ab)
    compare_ab.add_argument("--adaptive-combustion-a", choices=["as_is", "on", "off"], default="as_is")
    compare_ab.add_argument("--adaptive-combustion-b", choices=["as_is", "on", "off"], default="as_is")
    compare_ab.add_argument("--turbo-incremental-a", choices=["as_is", "on", "off"], default="as_is")
    compare_ab.add_argument("--turbo-incremental-b", choices=["as_is", "on", "off"], default="as_is")
    compare_ab.add_argument("--out", required=True, type=Path)

    sensitivity_local = sub.add_parser("sensitivity-local", help="Run local sensitivity around the current configuration on a dyno dataset")
    sensitivity_local.add_argument("--engine", required=True, type=Path)
    sensitivity_local.add_argument("--dataset", required=True, type=Path)
    sensitivity_local.add_argument("--params", type=str, default="ve_scale,friction_scale,burn_scale")
    _add_legacy_args(sensitivity_local)
    _add_adaptive_combustion_arg(sensitivity_local)
    _add_turbo_incremental_arg(sensitivity_local)
    sensitivity_local.add_argument("--out", required=True, type=Path)

    return parser


def main(argv: Iterable[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "dyno":
        run_dyno(
            args.engine,
            args.rpm,
            args.out,
            mode=args.mode,
            turbo_path=args.turbo,
            settle_cycles=args.settle_cycles,
            min_periodicity=args.min_periodicity,
            drop_invalid=args.drop_invalid,
            rpm_start_safe=args.rpm_start_safe,
            debug_dyno_v2=args.debug_dyno_v2,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
            knock_report=args.knock_report,
            adaptive_combustion=str(args.adaptive_combustion),
        )
    elif args.command == "scope":
        run_scope(
            args.engine,
            args.rpm,
            args.cycles,
            args.out,
            target_dx=args.target_dx,
            max_steps=args.max_steps,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "intake-scope":
        run_intake_scope(
            args.engine,
            args.out,
            max_steps=args.max_steps,
            target_dx=args.target_dx,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "audio":
        run_audio(
            args.engine,
            args.rpm,
            args.duration,
            args.sample_rate,
            args.out,
            args.firing_order,
            source=str(args.source),
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "sweep":
        run_sweep(
            args.engine,
            args.rpm,
            args.out,
            runner_lengths=_parse_length_list(args.runner_lengths),
            points=args.points,
            span_mm=args.span_mm,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "map":
        run_map(
            args.engine,
            _parse_float_list(args.rpm_grid),
            _parse_float_list(args.throttle_grid),
            args.out,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "calibrate":
        run_calibrate(
            args.engine,
            args.target,
            args.out,
            [p.strip() for p in str(args.params).split(",") if p.strip()],
            int(args.max_evals),
            diagnostics=bool(args.diagnostics),
            multi_start=int(args.multi_start),
            eps_obj=float(args.eps_obj),
            eps_params=float(args.eps_params),
            top_k=int(args.top_k),
            seed=int(args.seed),
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "calibrate-bmep":
        run_calibrate_bmep(
            args.engine,
            float(args.rpm),
            float(args.target_bmep),
            args.out,
            _parse_numeric_range(args.ca50_range, default_step=1.0),
            _parse_numeric_range(args.duration_range, default_step=2.0),
            wiebe_a=args.wiebe_a,
            wiebe_m=args.wiebe_m,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "optimize":
        run_optimize(
            args.engine,
            args.target,
            args.out,
            args.param,
            _parse_bounds(args.bounds),
            int(args.seed),
            int(args.max_evals),
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "optimize-guided":
        run_optimize_guided(
            args.engine,
            args.out,
            objective=str(args.objective),
            params=[p.strip() for p in str(args.params).split(",") if p.strip()],
            seed=int(args.seed),
            max_evals=int(args.max_evals),
            target_path=args.target,
            rpm_grid=_parse_float_list(args.rpm_grid),
            bounds_map=_parse_bounds_map_text(args.param_bounds),
            max_signal_mape=_parse_float_mapping_text(args.max_signal_mape),
            min_peak_power_hp=args.min_peak_power_hp,
            min_mean_torque_nm=args.min_mean_torque_nm,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "full-scope":
        run_full_scope(
            args.engine,
            args.duration,
            args.out,
            max_steps=args.max_steps,
            target_dx=args.target_dx,
            use_numba=bool(args.fast_numba),
            time_budget_ms=args.time_budget_ms,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "cutlist":
        engine_path = args.engine if args.engine is not None else args.preset
        run_cutlist(
            engine_path,
            args.out,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "selfcheck":
        sys.exit(run_selfcheck(args.expectations, args.out))
    elif args.command == "benchmark":
        run_benchmark(
            args.engine,
            args.dataset,
            args.out,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
            adaptive_combustion=str(args.adaptive_combustion),
        )
    elif args.command == "bench-import":
        run_bench_import(
            args.csv,
            args.out,
            dataset_id=str(args.dataset_id),
            engine_id=str(args.engine_id),
            preset_path=str(args.preset_path),
            torque_units=str(args.torque_units),
            power_units=str(args.power_units),
            notes=str(args.notes),
            torque_mape_max=float(args.torque_mape_max),
            power_mape_max=float(args.power_mape_max),
        )
    elif args.command == "dyno-import":
        run_dyno_import(
            args.input,
            args.out,
            dataset_id=str(args.dataset_id),
            engine_id=str(args.engine_id),
            preset_path=str(args.preset_path),
            source_format=str(args.format),
            mapping=str(args.mapping),
            units=str(args.units),
            notes=str(args.notes),
            torque_mape_max=float(args.torque_mape_max),
            power_mape_max=float(args.power_mape_max),
            afr_stoich=float(args.afr_stoich),
        )
    elif args.command == "dyno-compare":
        run_dyno_compare(
            args.engine,
            args.dataset,
            args.out,
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
            adaptive_combustion=str(args.adaptive_combustion),
        )
    elif args.command == "calibrate-staged":
        run_calibrate_staged(
            args.engine,
            args.dataset,
            args.out,
            max_evals_per_stage=int(args.max_evals_per_stage),
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
            adaptive_combustion=str(args.adaptive_combustion),
        )
    elif args.command == "validate-features":
        run_validate_features(
            args.engine,
            _parse_path_list(args.datasets),
            args.out,
            include_adaptive_toggle=bool(args.with_adaptive_toggle),
            include_turbo_toggle=bool(args.with_turbo_toggle),
            include_staged_calibration=bool(args.with_staged_calibration),
            max_evals_per_stage=int(args.max_evals_per_stage),
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "compare-ab":
        run_compare_ab(
            args.engine_a,
            args.engine_b,
            args.dataset,
            args.out,
            label_a=str(args.label_a),
            label_b=str(args.label_b),
            adaptive_combustion_a=str(args.adaptive_combustion_a),
            adaptive_combustion_b=str(args.adaptive_combustion_b),
            turbo_incremental_a=str(args.turbo_incremental_a),
            turbo_incremental_b=str(args.turbo_incremental_b),
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )
    elif args.command == "sensitivity-local":
        run_sensitivity_local(
            args.engine,
            args.dataset,
            args.out,
            params=[p.strip() for p in str(args.params).split(",") if p.strip()],
            adaptive_combustion=str(args.adaptive_combustion),
            turbo_incremental=str(args.turbo_incremental),
            legacy_compat=args.legacy_compat,
            auto_legacy_compat=bool(args.auto_legacy_compat),
        )


if __name__ == "__main__":
    main()
