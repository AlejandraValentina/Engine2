from __future__ import annotations

from core.engine_components import Engine
from core.engine_wizard import WizardSpec, build_engine_from_wizard
from core.thermo import CylinderSimulator


def test_engine_wizard_roundtrip_runs_simulator() -> None:
    spec = WizardSpec(
        complexity="Advanced",
        architecture="Inline-4",
        aspiration="Naturally Aspirated",
        rpm_start=2500,
        rpm_end=8000,
        objective="torque_mean",
        displacement_cc=2400.0,
        compression_ratio=11.2,
        runner_length_mm=380.0,
        header_length_mm=720.0,
    )

    engine = build_engine_from_wizard(spec)
    roundtrip = Engine.from_dict(engine.to_dict())
    result = CylinderSimulator(roundtrip).run_cycle(3500.0)

    assert roundtrip.preflight_validate_with_issues(operation="dyno", mode="v1") == []
    assert result["mean_power_hp"] > 0.0
    assert result["mean_torque_nm"] > 0.0
