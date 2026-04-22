from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

jsonschema = pytest.importorskip("jsonschema")

from core.engine_components import Engine


def test_knock_report_schema(tmp_path: Path) -> None:
    engine = Engine()
    engine.combustion.residual_coupling = {"enabled": True, "k": 0.8, "min_factor": 0.4}
    engine_path = tmp_path / "engine.json"
    engine.save_to_file(str(engine_path))

    dyno_path = tmp_path / "dyno.json"
    knock_path = tmp_path / "knock.json"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pywavedyn.cli",
            "dyno",
            "--engine",
            str(engine_path),
            "--rpm",
            "1500",
            "--mode",
            "v1",
            "--knock-report",
            str(knock_path),
            "--out",
            str(dyno_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(knock_path.read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/knock_report.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
