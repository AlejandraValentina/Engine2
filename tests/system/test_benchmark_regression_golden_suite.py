from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")
pytest.importorskip("numpy")


DATASETS = [
    ("presets/honda_k20.json", "benchmarks/datasets/k20_like_regression_golden"),
    ("presets/chevy_350.json", "benchmarks/datasets/v8_like_regression_golden"),
    ("presets/ferrari_f1.json", "benchmarks/datasets/f1_like_regression_golden"),
]


def _run_benchmark(tmp_path: Path, engine: Path, dataset: Path, tag: str) -> dict:
    out_path = tmp_path / f"bench_report_{tag}.json"
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
def test_benchmark_regression_golden_suite(tmp_path: Path) -> None:
    schema = json.loads(Path("schemas/bench_report.schema.json").read_text(encoding="utf-8"))

    for idx, (engine_path, dataset_path) in enumerate(DATASETS):
        engine = Path(engine_path).resolve()
        dataset = Path(dataset_path).resolve()

        payload_a = _run_benchmark(tmp_path, engine, dataset, f"{idx}_a")
        jsonschema.validate(instance=payload_a, schema=schema)
        assert payload_a["contract"]["pass"] is True

        payload_b = _run_benchmark(tmp_path, engine, dataset, f"{idx}_b")
        assert payload_a["metadata"]["input_hash"] == payload_b["metadata"]["input_hash"]
        assert payload_a["errors"]["total_mape"] == pytest.approx(payload_b["errors"]["total_mape"])
