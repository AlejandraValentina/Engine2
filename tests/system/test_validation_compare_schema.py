from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


@pytest.mark.system
def test_validation_compare_schema(tmp_path: Path) -> None:
    out_path = tmp_path / "validation_compare.json"
    preset = Path("presets/honda_k20.json").resolve()
    dataset = Path("benchmarks/datasets/k20_like_real").resolve()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "validate-features",
            "--engine",
            str(preset),
            "--datasets",
            str(dataset),
            "--out",
            str(out_path),
            "--with-adaptive-toggle",
            "--with-staged-calibration",
            "--max-evals-per-stage",
            "5",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/validation_compare.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["report_type"] == "validation_compare_report"
    assert payload["report_format_version"] == 1
    assert payload["report_family"] == "analysis"
    assert payload["context"]["dataset_id"] == "k20_like_real"
    assert payload["context"]["base_engine_path"] == str(preset)
    assert payload["cases"]
    assert payload["cases"][0]["signal_evidence"]["groups"]["contract_baseline"]["status"] == "compared"
    assert payload["cases"][0]["signal_evidence"]["groups"]["turbo"]["status"] == "not_available"
    assert "adaptive_on" in payload["cases"][0]["features"]
    assert "staged_after" in payload["cases"][0]["features"]
