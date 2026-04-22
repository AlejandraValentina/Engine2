import math

import core.calibrator as calibrator


def test_calibrator_recovers_const_fmep(monkeypatch) -> None:
    def fake_run(project_config: dict, rpm: float, cycles: int = 3, warm_start_state=None):
        fmep = float(project_config.get("brake_model", {}).get("fmep_pa", 0.0))
        eta = float(
            project_config.get("simulation_settings", {})
            .get("fuel", {})
            .get("eta_comb", 1.0)
        )
        base_torque = 200.0 + rpm * 0.01
        indicated_torque = base_torque * eta
        brake_torque = max(0.0, indicated_torque - fmep * 1e-3)
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

    true_cfg = {
        "calibration": {"enabled": True},
        "brake_model": {"fmep_pa": 100000.0},
        "simulation_settings": {"fuel": {"enabled": True, "eta_comb": 0.95}},
    }
    target_points = []
    for rpm in (2000, 3000, 4000):
        pred, _ = fake_run(true_cfg, rpm)
        target_points.append({"rpm": rpm, "brake_torque_nm": pred["brake_torque_nm"]})

    base_cfg = {
        "calibration": {"enabled": True},
        "brake_model": {"fmep_pa": 200000.0},
        "simulation_settings": {"fuel": {"enabled": True, "eta_comb": 0.95}},
    }

    initial_loss, _ = calibrator._evaluate_loss(base_cfg, {"fmep_pa": 200000.0}, target_points)
    result = calibrator.calibrate_to_curve(
        base_project_config=base_cfg,
        target_points=target_points,
        fit={"fmep": True, "eta_comb": False, "throttle_k": False},
        max_outer_iters=4,
        seed=0,
    )

    best_fmep = result["best_config"]["brake_model"]["fmep_pa"]
    assert result["best_loss"] < initial_loss
    assert abs(best_fmep - 100000.0) < 5000.0
