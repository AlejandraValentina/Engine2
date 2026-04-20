from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


@pytest.mark.integration
def test_benchmark_accepts_legacy_dataset_metadata(tmp_path: Path) -> None:
    out_path = tmp_path / "bench_report.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "benchmark",
            "--engine",
            str(Path("presets/honda_k20.json").resolve()),
            "--dataset",
            str(Path("benchmarks/datasets/honda_k20_na").resolve()),
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/bench_report.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["dataset"]["dataset_id"] == "honda_k20_na"
    assert payload["contract"]["pass"] is True
