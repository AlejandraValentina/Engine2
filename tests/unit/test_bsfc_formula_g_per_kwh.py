import core.advanced.orchestrator as orchestrator_module


def test_bsfc_formula_g_per_kwh() -> None:
    fuel_flow_kg_s = 1e-4
    brake_power_w = 10000.0
    bsfc = orchestrator_module._bsfc_g_per_kwh(fuel_flow_kg_s, brake_power_w)
    assert bsfc is not None
    assert abs(bsfc - 36.0) < 1e-9
