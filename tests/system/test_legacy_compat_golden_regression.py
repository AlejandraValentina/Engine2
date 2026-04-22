from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

RPM_SPEC = "2000:4000:1000"
DATASETS = [
    (
        "presets/legacy/custom_twin_230cc.json",
        "benchmarks/datasets/regression_golden/legacy_compat/custom_twin_230cc.json",
    ),
    (
        "presets/legacy/ferrari_355_v12.json",
        "benchmarks/datasets/regression_golden/legacy_compat/ferrari_355_v12.json",
    ),
    (
        "presets/legacy/chevy_350_legacy.json",
        "benchmarks/datasets/regression_golden/legacy_compat/chevy_350_legacy.json",
    ),
]


@pytest.mark.system
def test_legacy_compat_golden_regression(tmp_path: Path) -> None:
    for idx, (engine_path, golden_path) in enumerate(DATASETS):
        out_path = tmp_path / f"legacy_dyno_{idx}.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pywavedyn.cli",
                "dyno",
                "--engine",
                engine_path,
                "--rpm",
                RPM_SPEC,
                "--mode",
                "v1",
                "--auto-legacy-compat",
                "--out",
                str(out_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        payload = json.loads(out_path.read_text(encoding="utf-8"))
        gold = json.loads(Path(golden_path).read_text(encoding="utf-8"))

        results = payload.get("results", [])
        assert len(results) == len(gold["rpm"])

        for idx_result, rpm in enumerate(gold["rpm"]):
            assert results[idx_result]["rpm"] == pytest.approx(rpm, rel=1e-6)
            for key in ("mean_power_hp", "mean_torque_nm", "bmep_bar", "ve_actual"):
                assert results[idx_result][key] == pytest.approx(gold[key][idx_result], rel=1e-3, abs=1e-3)
