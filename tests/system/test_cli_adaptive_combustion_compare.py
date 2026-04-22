from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")


@pytest.mark.system
def test_cli_benchmark_reports_adaptive_combustion_override(tmp_path: Path) -> None:
    preset = tmp_path / "adaptive_engine.json"
    raw = json.loads(Path("presets/honda_k20.json").read_text(encoding="utf-8"))
    raw.setdefault("combustion", {})["adaptive_model"] = {
        "enabled": False,
        "duration_scale": 1.05,
        "ca50_offset_deg": -1.0,
    }
    preset.write_text(json.dumps(raw, indent=2), encoding="utf-8")

    report_off = tmp_path / "bench_off.json"
    report_on = tmp_path / "bench_on.json"
    dataset = Path("benchmarks/datasets/k20_like_real").resolve()

    for mode, out_path in (("off", report_off), ("on", report_on)):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pywavedyn.cli",
                "benchmark",
                "--engine",
                str(preset),
                "--dataset",
                str(dataset),
                "--adaptive-combustion",
                mode,
                "--out",
                str(out_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    off_payload = json.loads(report_off.read_text(encoding="utf-8"))
    on_payload = json.loads(report_on.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/bench_report.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=off_payload, schema=schema)
    jsonschema.validate(instance=on_payload, schema=schema)

    assert off_payload["metadata"]["combustion"]["adaptive_mode_requested"] == "off"
    assert off_payload["metadata"]["combustion"]["adaptive_enabled"] is False
    assert on_payload["metadata"]["combustion"]["adaptive_mode_requested"] == "on"
    assert on_payload["metadata"]["combustion"]["adaptive_enabled"] is True
    assert on_payload["metadata"]["combustion"]["adaptive_parameters"]["duration_scale"] == 1.05
