from __future__ import annotations

import pytest

pytest.importorskip("numpy")

import numpy as np

from core.engine_components import Engine, Pipe
from core.simulator import Engine1DSolver
from core.thermo import CylinderSimulator
from core.units import bar_to_pa
from core.wave_utils import build_exhaust_coupling


def _build_solver(engine: Engine) -> Engine1DSolver:
    exhaust = engine.exhaust
    n_cyl = max(engine.block.num_cylinders, 1)
    primaries = [
        Pipe(
            length=exhaust.header_primary_length,
            diameter_inlet=exhaust.header_primary_diameter,
            diameter_outlet=exhaust.header_primary_diameter,
        )
        for _ in range(n_cyl)
    ]
    tail_dia = exhaust.header_primary_diameter * max(np.sqrt(n_cyl) * 0.6, 1.2)
    tailpipe = Pipe(
        length=exhaust.collector_length,
        diameter_inlet=tail_dia,
        diameter_outlet=tail_dia,
    )
    return Engine1DSolver(
        primaries,
        tailpipe,
        engine.block.firing_order,
        settings=engine.simulation_settings,
        camshaft=engine.camshaft,
        head=engine.head,
        target_dx=0.04,
    )


def _reset_solver(solver: Engine1DSolver) -> None:
    for state in solver.primary_states:
        state["U"] = state["initial"].copy()
    solver.tail_state["U"] = solver.tail_state["initial"].copy()
    solver.time = 0.0


def _sample_backpressure_trace(
    solver: Engine1DSolver,
    rpm: float,
    coupling_data: dict[int, dict[str, np.ndarray]],
    cyl_id: int = 1,
    degrees: float = 180.0,
) -> dict[str, np.ndarray]:
    _reset_solver(solver)
    total_time = degrees / (max(rpm, 1.0) * 6.0)
    angles: list[float] = []
    pressures: list[float] = []

    while solver.time < total_time:
        base_angle = (solver.time * rpm * 6.0) % 720.0
        pressures_by_cyl = solver.get_exhaust_backpressure_by_cyl()
        angles.append(base_angle)
        pressures.append(float(pressures_by_cyl[cyl_id]))

        p_stag_by_cyl: dict[int, float] = {}
        t_stag_by_cyl: dict[int, float] = {}
        for cid in range(1, solver.n_cyl + 1):
            data = coupling_data.get(cid)
            if data is None:
                raise ValueError(f"Missing coupling data for cylinder {cid}")
            cyl_angle = (base_angle + solver.phase_map.get(cid, 0.0)) % 720.0
            p_stag_by_cyl[cid] = float(np.interp(cyl_angle, data["angle"], data["p_stag"]))
            t_stag_by_cyl[cid] = float(np.interp(cyl_angle, data["angle"], data["t_stag"]))

        dt = solver.get_time_step()
        solver.step(
            rpm=rpm,
            dt=dt,
            p_stag_by_cyl=p_stag_by_cyl,
            T_stag_by_cyl=t_stag_by_cyl,
        )

    angle_arr = np.asarray(angles, dtype=float)
    pressure_arr = np.asarray(pressures, dtype=float)
    if degrees < 720.0:
        repeat = int(round(720.0 / degrees))
        angle_segments = []
        pressure_segments = []
        for idx in range(repeat):
            angle_segments.append(angle_arr + idx * degrees)
            pressure_segments.append(pressure_arr)
        angle_arr = np.concatenate(angle_segments)
        pressure_arr = np.concatenate(pressure_segments)
    order = np.argsort(angle_arr)
    return {
        "angle": angle_arr[order],
        "pressure": pressure_arr[order],
    }


@pytest.mark.integration
@pytest.mark.slow
def test_0d_1d_bidirectional_backpressure_affects_cycle() -> None:
    engine = Engine.load_from_file("presets/legacy/custom_twin_230cc.json")
    engine.simulation_settings.enable_0d_to_1d_exhaust_coupling = True
    engine.exhaust.header_primary_length = max(engine.exhaust.header_primary_length, 1200.0)
    engine.exhaust.collector_length = max(engine.exhaust.collector_length, 1000.0)
    rpm = 3000.0

    baseline = CylinderSimulator(engine).run_cycle(rpm)
    coupling = build_exhaust_coupling(
        baseline["angle"],
        baseline["exhaust_p_stag"],
        baseline["exhaust_t_stag"],
        engine.block.firing_order,
    )

    solver = _build_solver(engine)
    backpressure_trace = _sample_backpressure_trace(solver, rpm, coupling, cyl_id=1, degrees=180.0)

    assert np.isfinite(backpressure_trace["pressure"]).all()
    assert float(np.min(backpressure_trace["pressure"])) > 0.0
    assert float(np.max(backpressure_trace["pressure"]) - np.min(backpressure_trace["pressure"])) > 1.0

    dynamic = CylinderSimulator(engine).run_cycle(rpm, exhaust_backpressure_trace=backpressure_trace)

    assert np.isfinite(dynamic["pressure"]).all()
    assert np.isfinite(dynamic["torque"]).all()
    assert float(np.min(dynamic["pressure"])) > 0.0

    baseline_torque = float(baseline["mean_torque_nm"])
    dynamic_torque = float(dynamic["mean_torque_nm"])
    assert abs(dynamic_torque - baseline_torque) > 1e-3

    ambient_pressure = bar_to_pa(getattr(engine.simulation_settings, "air_pressure_bar", 1.013))
    backpressure_factor = getattr(engine.simulation_settings, "exhaust_backpressure_factor", 1.05)
    baseline_bp = backpressure_factor * ambient_pressure

    cam = engine.camshaft
    ecl = 720.0 - (cam.lobe_separation + cam.advance)
    evo = float(np.clip(ecl - (cam.exhaust_duration / 2.0), 480.0, 720.0))
    mask_exhaust = backpressure_trace["angle"] >= evo
    if np.any(mask_exhaust):
        avg_dynamic_bp = float(np.mean(backpressure_trace["pressure"][mask_exhaust]))
    else:
        avg_dynamic_bp = float(np.mean(backpressure_trace["pressure"]))

    tol = 1e-6
    if avg_dynamic_bp > baseline_bp:
        assert dynamic_torque <= baseline_torque + tol
    else:
        assert dynamic_torque >= baseline_torque - tol
