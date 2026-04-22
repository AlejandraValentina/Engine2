from core.advanced.orchestrator import OrchestratorConfig, PipePrefillConfig, _init_pipe_state


def test_pipe_prefill_auto_sets_exhaust_defaults() -> None:
    cfg = OrchestratorConfig(
        pipe_role="exhaust",
        pipe_prefill=PipePrefillConfig(
            enabled=True,
            auto=True,
            auto_amb_p_Pa=101325.0,
            auto_amb_T_K=305.0,
            exhaust_prefill_T_K=700.0,
        ),
    )
    _, _, p0, T0, Y_init = _init_pipe_state(cfg, pipe_cells=5)

    assert abs(p0 - 101325.0) < 1e-9
    assert abs(T0 - 700.0) < 1e-9
    assert abs(Y_init - 0.0) < 1e-12


def test_pipe_prefill_auto_disabled_path_unchanged() -> None:
    base = OrchestratorConfig(pipe_role="intake")
    auto_disabled = OrchestratorConfig(
        pipe_role="intake",
        pipe_prefill=PipePrefillConfig(enabled=False, auto=True),
    )

    _, rho_base, p_base, T_base, Y_base = _init_pipe_state(base, pipe_cells=5)
    _, rho_auto, p_auto, T_auto, Y_auto = _init_pipe_state(auto_disabled, pipe_cells=5)

    assert abs(rho_base - rho_auto) < 1e-12
    assert abs(p_base - p_auto) < 1e-12
    assert abs(T_base - T_auto) < 1e-12
    assert abs(Y_base - Y_auto) < 1e-12
