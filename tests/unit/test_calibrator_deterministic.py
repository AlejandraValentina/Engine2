import math

import core.calibrator as calibrator


def test_calibrator_deterministic(monkeypatch) -> None:
    def fake_run(project_config: dict, rpm: float, cycles: int = 3, warm_start_state=None):
        fmep = float(project_config.get("brake_model", {}).get("fmep_pa", 0.0))
        base_torque = 180.0 + rpm * 0.02
        brake_torque = max(0.0, base_torque - fmep * 1e-3)
        omega = rpm * 2.0 * math.pi / 60.0
        return (
            {
                "rpm": rpm,
                "brake_torque_nm": brake_torque,
                "brake_power_w": brake_torque * omega,
            },
            warm_start_state,
        )

    monkeypatch.setattr(calibrator, "run_advanced_single_point", fake_run)

    target_cfg = {
        "calibration": {"enabled": True},
        "brake_model": {"fmep_pa": 90000.0},
    }
    target_points = []
    for rpm in (2500, 3500):
        pred, _ = fake_run(target_cfg, rpm)
        target_points.append({"rpm": rpm, "brake_power_w": pred["brake_power_w"]})

    base_cfg = {
        "calibration": {"enabled": True},
        "brake_model": {"fmep_pa": 200000.0},
    }

    result_a = calibrator.calibrate_to_curve(
        base_project_config=base_cfg,
        target_points=target_points,
        fit={"fmep": True, "eta_comb": False, "throttle_k": False},
        max_outer_iters=3,
        seed=42,
    )
    result_b = calibrator.calibrate_to_curve(
        base_project_config=base_cfg,
        target_points=target_points,
        fit={"fmep": True, "eta_comb": False, "throttle_k": False},
        max_outer_iters=3,
        seed=42,
    )

    assert result_a["best_loss"] == result_b["best_loss"]
    assert result_a["best_config"]["brake_model"]["fmep_pa"] == result_b["best_config"]["brake_model"]["fmep_pa"]
