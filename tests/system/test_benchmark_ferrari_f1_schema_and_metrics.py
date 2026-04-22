from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
pytest.importorskip("numpy")


def _run_benchmark(tmp_path: Path, engine: Path, dataset: Path) -> dict:
    out_path = tmp_path / "bench_report.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "benchmark",
            "--engine",
            str(engine),
            "--dataset",
            str(dataset),
            "--out",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out_path.read_text(encoding="utf-8"))


@pytest.mark.system
def test_benchmark_ferrari_f1_schema_and_metrics(tmp_path: Path) -> None:
    engine = Path("presets/ferrari_f1.json").resolve()
    dataset = Path("benchmarks/datasets/ferrari_f1_na").resolve()

    payload_a = _run_benchmark(tmp_path, engine, dataset)
    schema = json.loads(Path("schemas/bench_report.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload_a, schema=schema)
    assert payload_a["contract"]["pass"] is True

    payload_b = _run_benchmark(tmp_path, engine, dataset)
    assert payload_a["metadata"]["input_hash"] == payload_b["metadata"]["input_hash"]
    assert payload_a["errors"]["total_mape"] == pytest.approx(payload_b["errors"]["total_mape"])
