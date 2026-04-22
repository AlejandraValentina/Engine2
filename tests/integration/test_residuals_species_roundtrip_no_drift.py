import pytest

np = pytest.importorskip("numpy")

from core.engine_components import Engine, Pipe
from core.simulator import Engine1DSolver
from core.thermo import CylinderSimulator
from core.wave_utils import build_exhaust_coupling


def _build_wave_solver(engine: Engine, target_dx: float = 0.05) -> Engine1DSolver:
    exhaust = engine.exhaust
    block = engine.block

    n_cyl = max(block.num_cylinders, 1)
    primaries = []
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
        target_dx=target_dx,
    )


def test_residuals_species_roundtrip_no_drift() -> None:
    engine = Engine()
    engine.simulation_settings.species.enabled = True
    engine.simulation_settings.enable_0d_to_1d_exhaust_coupling = True
    engine.combustion.residual_coupling = {"enabled": True, "k": 0.8, "min_factor": 0.4}

    rpm = 2500.0
    simulator = CylinderSimulator(engine)
    cycle = simulator.run_cycle(rpm)
    coupling = build_exhaust_coupling(
        cycle["angle"],
        cycle["exhaust_p_stag"],
        cycle["exhaust_t_stag"],
        engine.block.firing_order,
    )

    solver = _build_wave_solver(engine)

    for _ in range(6):
        dt = solver.get_time_step()
        p_stag_by_cyl = {}
        t_stag_by_cyl = {}
        base_angle = (solver.time * rpm * 6.0) % 720.0
        for cyl_id in range(1, solver.n_cyl + 1):
            data = coupling.get(cyl_id)
            assert data is not None
            cyl_angle = (base_angle + solver.phase_map.get(cyl_id, 0.0)) % 720.0
            angle_arr = data["angle"]
            p_arr = data["p_stag"]
            t_arr = data["t_stag"]
            p_stag_by_cyl[cyl_id] = float(np.interp(cyl_angle, angle_arr, p_arr))
            t_stag_by_cyl[cyl_id] = float(np.interp(cyl_angle, angle_arr, t_arr))

        solver.step(
            rpm=rpm,
            dt=dt,
            p_stag_by_cyl=p_stag_by_cyl,
            T_stag_by_cyl=t_stag_by_cyl,
        )

        total_rho = 0.0
        total_rhoY = 0.0
        for state in solver.primary_states + [solver.tail_state]:
            U = state["U"]
            total_rho += float(np.sum(U[:, 0]) * state["dx"])
            total_rhoY += float(np.sum(U[:, 3]) * state["dx"])
            assert np.isfinite(U).all()

        ratio = total_rhoY / max(total_rho, 1e-12)
        assert -1e-6 <= ratio <= 1.0 + 1e-6
