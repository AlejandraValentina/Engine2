from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


@pytest.mark.system
def test_optimize_guided_schema(tmp_path: Path) -> None:
    preset = Path("presets/legacy/custom_twin_230cc.json").resolve()
    target_path = tmp_path / "target.json"
    out_path = tmp_path / "optimize_guided.json"
    target_path.write_text(
        json.dumps(
            {
                "points": [
                    {"rpm": 2500, "power_hp": 15.0},
                    {"rpm": 3500, "power_hp": 19.0}
                ]
            }
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "optimize-guided",
            "--engine",
            str(preset),
            "--objective",
            "dataset_error",
            "--params",
            "burn_scale,friction_scale",
            "--target",
            str(target_path),
            "--max-signal-mape",
            "power_hp=1.0",
            "--max-evals",
            "8",
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/optimize_guided.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["report_type"] == "optimize_guided_report"
    assert payload["report_format_version"] == 1
    assert payload["report_family"] == "analysis"
    assert payload["context"]["engine_path"] == str(preset)
    assert payload["optimization_problem"]["objective"] == "dataset_error"
