import json
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("numpy")


def test_selfcheck_cli(tmp_path: Path) -> None:
    case_path = tmp_path / "case.json"
    expectations_path = tmp_path / "expectations.json"
    report_path = tmp_path / "report.json"

    case_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_name": "Selfcheck Tiny",
                "block": {
                    "bore": 86.0,
                    "stroke": 86.0,
                    "conrod_length": 139.0,
                    "num_cylinders": 1,
                    "config": "L",
                    "bank_angle": 0.0,
                    "firing_order": [1],
                    "redline_rpm": 7000.0,
                },
                "head": {
                    "compression_ratio": 10.0,
                    "intake_valves": 2,
                    "exhaust_valves": 1,
                    "intake_valve_diameter": 34.0,
                    "exhaust_valve_diameter": 30.0,
                    "port_flow_cfm": 150.0,
                    "port_flow_efficiency": 0.7,
                    "mach_tolerance": 0.75,
                },
                "camshaft": {
                    "intake_lift": 10.0,
                    "exhaust_lift": 9.0,
                    "intake_duration": 240.0,
                    "exhaust_duration": 240.0,
                    "lobe_separation": 110.0,
                    "advance": 0.0,
                    "peak_rpm": 5000.0,
                },
                "intake": {
                    "runner_length": 200.0,
                    "runner_diameter": 40.0,
                    "plenum_volume": 2.0,
                    "throttle_body_dia": 60.0,
                    "throttle_cfm": 300.0,
                    "flow_loss_coefficient": 0.0,
                },
                "exhaust": {
                    "header_primary_length": 600.0,
                    "header_primary_diameter": 38.0,
                    "collector_length": 200.0,
                },
                "combustion": {
                    "thermal_efficiency": 0.5,
                    "burn_duration": 50.0,
                    "ignition_advance": 28.0,
                    "afr": 13.5,
                    "wiebe_a": 5.0,
                    "wiebe_m": 2.0,
                    "chamber_type": "Custom",
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    expectations_path.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "file": "case.json",
                        "rpm": [3000],
                        "power_hp_min": [0.0],
                        "power_hp_max": [500.0],
                    }
                ]
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "selfcheck",
            "--expectations",
            str(expectations_path),
            "--out",
            str(report_path),
        ]
    )
    assert proc.returncode == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["cases"]
    metadata = report["cases"][0]["metadata"]
    assert "input_hash" in metadata
    assert "settings" in metadata
    assert "coupling_mode" in metadata
