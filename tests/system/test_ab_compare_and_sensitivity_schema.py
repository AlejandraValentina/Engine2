from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


@pytest.mark.system
def test_ab_compare_and_sensitivity_schemas(tmp_path: Path) -> None:
    preset = Path("presets/honda_k20.json").resolve()
    dataset = Path("benchmarks/datasets/k20_like_real").resolve()
    compare_out = tmp_path / "ab_compare.json"
    sensitivity_out = tmp_path / "sensitivity_local.json"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "compare-ab",
            "--engine-a",
            str(preset),
            "--engine-b",
            str(preset),
            "--dataset",
            str(dataset),
            "--label-a",
            "baseline",
            "--label-b",
            "adaptive_on",
            "--adaptive-combustion-b",
            "on",
            "--out",
            str(compare_out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "sensitivity-local",
            "--engine",
            str(preset),
            "--dataset",
            str(dataset),
            "--params",
            "ve_scale,friction_scale,burn_scale",
            "--out",
            str(sensitivity_out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    ab_payload = json.loads(compare_out.read_text(encoding="utf-8"))
    sensitivity_payload = json.loads(sensitivity_out.read_text(encoding="utf-8"))
    ab_schema = json.loads(Path("schemas/ab_compare.schema.json").read_text(encoding="utf-8"))
    sensitivity_schema = json.loads(Path("schemas/sensitivity_local.schema.json").read_text(encoding="utf-8"))

    jsonschema.validate(instance=ab_payload, schema=ab_schema)
    jsonschema.validate(instance=sensitivity_payload, schema=sensitivity_schema)
    assert ab_payload["report_type"] == "ab_compare_report"
    assert ab_payload["report_family"] == "analysis"
    assert ab_payload["context"]["dataset_id"] == "k20_like_real"
    assert sensitivity_payload["report_type"] == "sensitivity_local_report"
    assert sensitivity_payload["report_family"] == "analysis"
    assert sensitivity_payload["context"]["dataset_id"] == "k20_like_real"
    assert sensitivity_payload["context"]["engine_path"] == str(preset)
    assert ab_payload["signal_evidence"]["groups"]["turbo"]["status"] == "not_available"
    assert sensitivity_payload["signal_evidence"]["groups"]["contract_baseline"]["status"] == "compared"
    assert ab_payload["comparison"]["labels"]["a"] == "baseline"
    assert sensitivity_payload["params"]
