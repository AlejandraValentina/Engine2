import math

from core.advanced.orchestrator import (
    OrchestratorConfig,
    PipePrefillConfig,
    PipePrefillState,
    _init_pipe_state,
)


def test_pipe_prefill_default_unchanged() -> None:
    cfg = OrchestratorConfig(pipe_role="intake")
    U, rho0, p0, T0, Y_init = _init_pipe_state(cfg, pipe_cells=5)
    expected_T0 = p0 / (rho0 * cfg.gas_constant)

    assert abs(rho0 - 1.2) < 1e-12
    assert abs(T0 - expected_T0) < 1e-12
    assert abs(Y_init - 1.0) < 1e-12
    assert abs(U[1, 0] - rho0) < 1e-12
    assert abs(U[1, 3] / U[1, 0] - 1.0) < 1e-12


def test_pipe_prefill_exhaust_temp_override() -> None:
    cfg = OrchestratorConfig(
        pipe_role="exhaust",
        pipe_prefill=PipePrefillConfig(
            enabled=True,
            intake=PipePrefillState(),
            exhaust=PipePrefillState(p_Pa=101325.0, T_K=700.0, Y=0.0),
        ),
    )
    U, rho0, p0, T0, Y_init = _init_pipe_state(cfg, pipe_cells=5)
    T_from_state = p0 / (rho0 * cfg.gas_constant)

    assert math.isfinite(T_from_state)
    assert abs(T0 - 700.0) < 1e-9
    assert abs(T_from_state - 700.0) < 1e-9
    assert abs(Y_init - 0.0) < 1e-12
    assert abs(U[1, 3]) < 1e-12
